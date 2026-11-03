"""Exact-operation Docker custody for the isolated Drone rollback rehearsal.

Independently pinned copy of the reviewed owner lifecycle pattern. A missing
client response is never proof that a daemon request did not create a container.
No provider credentials, runtime environment files or live databases enter it.
"""

import hashlib
import json
import os
import re
import subprocess
from uuid import UUID

import oracle_drone as r

LABEL = "org.onesa.release-operation"


def docker(*args, data=None, timeout=30):
    result = subprocess.run(
        ["/usr/bin/docker", *map(str, args)],
        input=data,
        capture_output=True,
        timeout=timeout,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    r.require(
        result.returncode == 0 and len(result.stdout) <= 8 * 1024 * 1024,
        "DRONE_ROLLBACK_DOCKER_OUTCOME_UNCONFIRMED",
    )
    return result.stdout


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write(path, value):
    r.write(path, value)
    sync_directory(path.parent)


def inventory(expression):
    """Only a successful bounded daemon inventory can establish absence."""
    rows = (
        docker(
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--filter",
            expression,
            "--format",
            "{{.ID}}",
            timeout=10,
        )
        .decode()
        .splitlines()
    )
    r.require(
        len(rows) <= 6
        and len(rows) == len(set(rows))
        and all(re.fullmatch(r"[a-f0-9]{64}", row) for row in rows),
        "DRONE_ROLLBACK_INVENTORY_CHANGED",
    )
    return set(rows)


class OwnedContainer:
    """One fresh, named container; no retry or removal by mutable name."""

    def __init__(
        self,
        folder,
        operation,
        role,
        image,
        *,
        binds=(),
        tmpfs=None,
        memory=768,
        pids=128,
        user="10001:10001",
    ):
        r.require(
            str(UUID(operation)) == operation
            and re.fullmatch(r"[a-z-]+", role)
            and re.fullmatch(r"sha256:[a-f0-9]{64}", image),
            "DRONE_ROLLBACK_CONTAINER_SCOPE",
        )
        self.name = "onesa-drone-rollback-" + UUID(operation).hex + "-" + role
        self.cidfile = folder / ("drone-rollback-" + role + ".cid")
        self.operation, self.role, self.image = operation, role, image
        self.binds = sorted((str(source), target, rw) for source, target, rw in binds)
        self.tmpfs = tmpfs or {"/tmp": "rw,mode=1777,size=256m"}
        self.memory, self.pids = memory, pids
        r.require(user in {"70:70", "10001:10001"}, "DRONE_ROLLBACK_RUNTIME_USER")
        self.user = user
        self.cid = None
        self.file_identity = None
        self.attempted = False
        self.entrypoint = None
        self.arguments = None
        self.environment = None

    def descriptor(self):
        return {
            "name": self.name,
            "cidfile": self.cidfile.name,
            "image_id": self.image,
            "operation_id": self.operation,
            "role": self.role,
            "network": "none",
            "binds": self.binds,
            "tmpfs": self.tmpfs,
            "user": self.user,
            "memory": self.memory * 1024**2,
            "pids": self.pids,
        }

    def read_cid(self):
        if not self.cidfile.exists():
            r.require(
                not self.cidfile.is_symlink() and self.file_identity is None,
                "DRONE_ROLLBACK_CID_CHANGED",
            )
            return None
        path = r.private(self.cidfile)
        before = path.stat()
        r.require(before.st_size in {64, 65} and before.st_nlink == 1, "DRONE_ROLLBACK_CID_FILE")
        value = path.read_text().strip()
        after = path.stat()
        observed = (before.st_dev, before.st_ino, before.st_mtime_ns, value)
        r.require(
            re.fullmatch(r"[a-f0-9]{64}", value)
            and after.st_nlink == 1
            and (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size)
            == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)
            and (self.file_identity is None or self.file_identity == observed)
            and (self.cid is None or self.cid == value),
            "DRONE_ROLLBACK_CID_CHANGED",
        )
        self.file_identity, self.cid = observed, value
        return value

    def inspect_owned(self, cid):
        rows = json.loads(docker("inspect", cid, timeout=10))
        r.require(
            isinstance(rows, list) and len(rows) == 1,
            "DRONE_ROLLBACK_CONTAINER_CHANGED",
        )
        row = rows[0]
        host, config = row["HostConfig"], row["Config"]
        actual_binds = []
        destinations = []
        for mount in row["Mounts"]:
            destinations.append(mount["Destination"])
            if mount["Type"] == "bind":
                actual_binds.append((mount["Source"], mount["Destination"], mount["RW"]))
            else:
                r.require(
                    mount["Type"] == "tmpfs" and mount["Destination"] in self.tmpfs and mount["RW"] is True,
                    "DRONE_ROLLBACK_CONTAINER_MOUNT_CHANGED",
                )
        binds = [source + ":" + target + (":rw" if rw else ":ro") for source, target, rw in self.binds]
        r.require(
            row["Id"] == cid
            and row["Name"] == "/" + self.name
            and row["Image"] == self.image
            and config.get("Labels", {}).get(LABEL) == self.operation
            and config.get("Labels", {}).get("org.onesa.rollback-role") == self.role
            and config["User"] == self.user
            and config["Entrypoint"] == [self.entrypoint]
            and config["Cmd"] == self.arguments
            and set(self.environment).issubset(config["Env"])
            and host["NetworkMode"] == "none"
            and set(row["NetworkSettings"].get("Networks", {})) <= {"none"}
            and not host.get("PortBindings")
            and not host.get("PublishAllPorts")
            and host["AutoRemove"] is False
            and host["ReadonlyRootfs"] is True
            and host["Privileged"] is False
            and host.get("CapAdd") in [None, []]
            and host["CapDrop"] == ["ALL"]
            and host["SecurityOpt"] == ["no-new-privileges:true"]
            and host["Memory"] == self.memory * 1024**2
            and host["NanoCpus"] == 1_000_000_000
            and host["PidsLimit"] == self.pids
            and host.get("Tmpfs", {}) == self.tmpfs
            and sorted(host.get("Binds") or []) == binds
            and sorted(actual_binds) == self.binds
            and len(destinations) == len(set(destinations))
            and type(row["State"]["Running"]) is bool,
            "DRONE_ROLLBACK_CONTAINER_CHANGED",
        )
        return row

    def observe(self):
        """Reconcile a CID file with exact name inventory after any CLI outcome."""
        self.read_cid()
        named = inventory("name=^/" + self.name + "$")
        r.require(len(named) <= 1, "DRONE_ROLLBACK_NAME_CHANGED")
        if not self.attempted:
            r.require(
                not named and self.cid is None,
                "DRONE_ROLLBACK_UNEXPECTED_CONTAINER",
            )
            return None
        if self.cid is None and named:
            recovered = next(iter(named))
            self.inspect_owned(recovered)
            self.cid = recovered
        if self.cid is None:
            # A timed-out create may still be pending at the daemon. An absent
            # CID file plus an empty inventory does not resolve that ambiguity.
            r.require(not self.attempted, "DRONE_ROLLBACK_CREATE_UNCONFIRMED")
            return None
        identified = inventory("id=" + self.cid)
        r.require(
            identified in [set(), {self.cid}] and named == identified,
            "DRONE_ROLLBACK_NAME_CID_MISMATCH",
        )
        return self.inspect_owned(self.cid) if identified else None

    def run(
        self,
        entrypoint,
        arguments,
        *,
        environment=(),
        data=None,
        detached=False,
        timeout=120,
    ):
        r.require(not self.attempted, "DRONE_ROLLBACK_CREATE_MUST_NOT_RETRY")
        self.entrypoint, self.arguments = entrypoint, list(arguments)
        self.environment = list(environment)
        write(
            self.cidfile.with_suffix(".intent.json"),
            {
                **self.descriptor(),
                "entrypoint": entrypoint,
                "command_sha256": hashlib.sha256(r.canonical(self.arguments)).hexdigest(),
                "input_sha256": hashlib.sha256(data or b"").hexdigest(),
                "automatic_retry": False,
            },
        )
        args = [
            "run",
            "-d" if detached else "-i",
            "--pull=never",
            "--name",
            self.name,
            "--cidfile",
            str(self.cidfile),
            "--label",
            LABEL + "=" + self.operation,
            "--label",
            "org.onesa.rollback-role=" + self.role,
            "--network",
            "none",
            "--read-only",
            "--no-healthcheck",
            "--user",
            self.user,
            "--memory",
            str(self.memory) + "m",
            "--cpus",
            "1",
            "--pids-limit",
            str(self.pids),
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
        ]
        for destination, options in self.tmpfs.items():
            args.extend(["--tmpfs", destination + ":" + options])
        for source, target, rw in self.binds:
            args.extend(["-v", source + ":" + target + (":rw" if rw else ":ro")])
        for value in environment:
            args.extend(["-e", value])
        args.extend(["--entrypoint", entrypoint, self.image, *arguments])
        self.attempted = True
        previous = os.umask(0o077)
        try:
            response = docker(*args, data=data, timeout=timeout)
        finally:
            os.umask(previous)
        r.require(self.read_cid() is not None, "DRONE_ROLLBACK_CID_FILE_MISSING")
        observed = self.observe()
        r.require(
            observed is not None
            and observed["State"]["Running"] is detached
            and (detached or observed["State"]["ExitCode"] == 0)
            and (not detached or response.decode().strip() == self.cid),
            "DRONE_ROLLBACK_CONTAINER_EXECUTION_UNCONFIRMED",
        )
        return response


def cleanup_owned(containers, operation):
    """Validate every ownership boundary before any single-CID removal."""
    observed = {}
    for container in containers:
        row = container.observe()
        if row is not None:
            r.require(container.attempted, "DRONE_ROLLBACK_UNEXPECTED_CONTAINER")
            observed[container.cid] = container
    r.require(
        inventory("label=" + LABEL + "=" + operation) == set(observed),
        "DRONE_ROLLBACK_OPERATION_INVENTORY_CHANGED",
    )
    errors = []
    for cid, container in reversed(list(observed.items())):
        # Never remove by name, nor retry a timed-out remove. If that one request
        # fails, still perform read-only observations and preserve its failure.
        container.inspect_owned(cid)
        try:
            docker("rm", "-f", cid, timeout=30)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            errors.append(error)
        r.require(
            container.observe() is None,
            "DRONE_ROLLBACK_CONTAINER_REMOVAL_UNCONFIRMED",
        )
    r.require(
        not inventory("label=" + LABEL + "=" + operation)
        and all(container.observe() is None for container in containers),
        "DRONE_ROLLBACK_FINAL_ABSENCE_UNCONFIRMED",
    )
    if errors:
        raise errors[0]
