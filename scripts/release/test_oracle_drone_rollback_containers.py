"""Independent fault tests for the isolated Drone container custody boundary."""

import copy
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import oracle_drone as d
import oracle_drone_rollback_containers as custody


class Daemon:
    """Keep daemon state separate from acknowledged client command results."""

    def __init__(self):
        self.rows = {}
        self.calls = []
        self.removed = []
        self.before_run = self.after_run = self.before_remove = None
        self.before_inventory = self.before_inspect = None
        self.serial = 0

    @staticmethod
    def values(args, flag):
        return [args[i + 1] for i, arg in enumerate(args[:-1]) if arg == flag]

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if args[0] == "run":
            cidfile = Path(self.values(args, "--cidfile")[0])
            intent = json.loads(cidfile.with_suffix(".intent.json").read_text())
            assert intent["name"] == self.values(args, "--name")[0]
            assert intent["automatic_retry"] is False
            if self.before_run:
                self.before_run(args, cidfile)
            self.serial += 1
            cid = f"{self.serial:064x}"
            entrypoint = args.index("--entrypoint")
            binds = self.values(args, "-v")
            tmpfs = dict(value.split(":", 1) for value in self.values(args, "--tmpfs"))
            row = {
                "Id": cid,
                "Name": "/" + intent["name"],
                "Image": args[entrypoint + 2],
                "Config": {
                    "Labels": dict(value.split("=", 1) for value in self.values(args, "--label")),
                    "User": self.values(args, "--user")[0],
                    "Entrypoint": [args[entrypoint + 1]],
                    "Cmd": list(args[entrypoint + 3 :]),
                    "Env": self.values(args, "-e"),
                },
                "HostConfig": {
                    "NetworkMode": self.values(args, "--network")[0],
                    "PortBindings": {},
                    "PublishAllPorts": False,
                    "AutoRemove": "--rm" in args,
                    "ReadonlyRootfs": "--read-only" in args,
                    "Privileged": False,
                    "CapAdd": [],
                    "CapDrop": self.values(args, "--cap-drop"),
                    "SecurityOpt": self.values(args, "--security-opt"),
                    "Memory": int(self.values(args, "--memory")[0][:-1]) * 1024**2,
                    "NanoCpus": int(self.values(args, "--cpus")[0]) * 1_000_000_000,
                    "PidsLimit": int(self.values(args, "--pids-limit")[0]),
                    "Binds": binds,
                    "Tmpfs": tmpfs,
                },
                "Mounts": [
                    {"Type": "bind", "Source": source, "Destination": target, "RW": mode == "rw"}
                    for source, target, mode in (value.split(":") for value in binds)
                ]
                + [{"Type": "tmpfs", "Destination": destination, "RW": True} for destination in tmpfs],
                "NetworkSettings": {"Networks": {"none": {}}},
                "State": {"Running": "-d" in args, "ExitCode": 0},
            }
            self.rows[cid] = row
            cidfile.write_text(cid + "\n")
            cidfile.chmod(0o600)
            if self.after_run:
                self.after_run(row, cidfile)
            return (cid + "\n").encode() if "-d" in args else b"synthetic-application-output"
        if args[:2] == ("container", "ls"):
            expression = self.values(args, "--filter")[0]
            if self.before_inventory:
                self.before_inventory(expression)
            if expression.startswith("id="):
                rows = [row for row in self.rows.values() if row["Id"] == expression[3:]]
            elif expression.startswith("name="):
                rows = [row for row in self.rows.values() if re.fullmatch(expression[5:], row["Name"])]
            else:
                key, value = expression.removeprefix("label=").split("=", 1)
                rows = [row for row in self.rows.values() if row["Config"]["Labels"].get(key) == value]
            return "".join(row["Id"] + "\n" for row in rows).encode()
        if args[0] == "inspect":
            if self.before_inspect:
                self.before_inspect(args[1])
            if args[1] not in self.rows:
                raise ValueError("SYNTHETIC_INSPECT_NOT_FOUND")
            return d.canonical([self.rows[args[1]]])
        if args[:2] == ("rm", "-f"):
            cid = args[2]
            if self.before_remove:
                self.before_remove(cid)
            self.removed.append(cid)
            del self.rows[cid]
            return (cid + "\n").encode()
        raise AssertionError("Unexpected synthetic Docker call")


class RollbackContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/root" if os.getuid() == 0 else None)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.operation = str(uuid4())
        self.image = "sha256:" + "a" * 64
        self.daemon = Daemon()
        self.enterContext(patch.object(custody, "docker", side_effect=self.daemon))
        if os.getuid() != 0:
            # CI fixtures use their actual account. Keep custody type, permission
            # and alias checks; no host installation or owner credential is read.
            def private(path, directory=False):
                selected = Path(path)
                observed = selected.lstat()
                d.require(
                    selected.is_relative_to(self.folder)
                    and not any(item.is_symlink() for item in [selected, *selected.parents])
                    and observed.st_uid == os.getuid()
                    and observed.st_mode & 0o077 == 0
                    and (stat.S_ISDIR(observed.st_mode) if directory else stat.S_ISREG(observed.st_mode)),
                    "SYNTHETIC_PRIVATE_CUSTODY",
                )
                return selected

            self.enterContext(patch.object(d, "private", side_effect=private))

    def owned(self, role="application", *, user="10001:10001"):
        folder = Path(tempfile.mkdtemp(dir=self.folder))
        return custody.OwnedContainer(
            folder,
            self.operation,
            role,
            self.image,
            binds=[(folder / "socket", "/var/run/postgresql", user == "70:70")],
            user=user,
        )

    def launch(self, item, *, detached=False):
        return item.run(
            "postgres" if detached else "python",
            ["--synthetic-fixture"],
            environment=["HOME=/tmp"],
            data=None if detached else b"synthetic-only-input",
            detached=detached,
        )

    def test_distinct_nonroot_users_and_durable_intent_precede_creation(self):
        events = []
        original = os.fsync

        def synced(fd):
            events.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
            return original(fd)

        def before(args, cidfile):
            self.assertEqual(events[-2:], ["file", "directory"])
            self.assertEqual(stat.S_IMODE(cidfile.with_suffix(".intent.json").stat().st_mode), 0o600)

        self.daemon.before_run = before
        items = [self.owned("database", user="70:70"), self.owned()]
        with patch.object(os, "fsync", side_effect=synced):
            self.launch(items[0], detached=True)
            self.launch(items[1])
        self.assertEqual(
            {row["Config"]["User"] for row in self.daemon.rows.values()}, {"70:70", "10001:10001"}
        )
        custody.cleanup_owned(items, self.operation)
        self.assertEqual(self.daemon.removed, [items[1].cid, items[0].cid])
        self.assertFalse(self.daemon.rows)
        for args, _ in self.daemon.calls:
            if args[0] == "run":
                self.assertNotIn("--rm", args)
                self.assertNotIn("--env-file", args)
                self.assertNotIn("-p", args)
                self.assertIn("--pull=never", args)
                self.assertIn("--read-only", args)

    def test_root_or_unqualified_user_never_creates_a_container(self):
        for user in ["0", "0:0", "root", "70:0", "999:999"]:
            with self.subTest(user=user), self.assertRaisesRegex(ValueError, "RUNTIME_USER"):
                self.owned(user=user)
        self.assertFalse(self.daemon.calls)

    def test_timeout_after_each_owned_role_creation_is_reconciled_without_retry(self):
        for role in ["schema", "database", "staging-seed", "production-verify"]:
            with self.subTest(role=role):
                item = self.owned(role, user="70:70" if role == "database" else "10001:10001")

                def interrupted(row, cidfile):
                    raise subprocess.TimeoutExpired("synthetic-docker", 1)

                self.daemon.after_run = interrupted
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.launch(item, detached=role == "database")
                custody.cleanup_owned([item], self.operation)
                self.assertFalse(self.daemon.rows)
                self.assertEqual(self.daemon.removed.count(item.cid), 1)
                with self.assertRaisesRegex(ValueError, "MUST_NOT_RETRY"):
                    self.launch(item)

    def test_no_cid_after_timeout_recovers_only_the_exact_owned_named_container(self):
        item = self.owned()

        def interrupted(row, cidfile):
            cidfile.unlink()
            raise subprocess.TimeoutExpired("synthetic-docker", 1)

        self.daemon.after_run = interrupted
        with self.assertRaises(subprocess.TimeoutExpired):
            self.launch(item)
        custody.cleanup_owned([item], self.operation)
        self.assertFalse(self.daemon.rows)
        self.assertEqual(self.daemon.removed, [item.cid])

    def test_pending_create_without_cid_or_inventory_remains_uncertain(self):
        item = self.owned()

        def interrupted(args, cidfile):
            raise subprocess.TimeoutExpired("synthetic-docker", 1)

        self.daemon.before_run = interrupted
        with self.assertRaises(subprocess.TimeoutExpired):
            self.launch(item)
        with self.assertRaisesRegex(ValueError, "CREATE_UNCONFIRMED"):
            custody.cleanup_owned([item], self.operation)
        self.assertFalse(self.daemon.removed)
        with self.assertRaisesRegex(ValueError, "MUST_NOT_RETRY"):
            self.launch(item)

    def test_normal_client_success_requires_its_cid_file(self):
        item = self.owned()
        self.daemon.after_run = lambda row, cidfile: cidfile.unlink()
        with self.assertRaisesRegex(ValueError, "CID_FILE_MISSING"):
            self.launch(item)
        custody.cleanup_owned([item], self.operation)
        self.assertFalse(self.daemon.rows)

    def test_successful_remove_requires_positive_absence_readback(self):
        item = self.owned()
        self.launch(item)
        original = self.daemon.__call__

        def incomplete(*args, **kwargs):
            if args[:2] == ("rm", "-f"):
                return b"success-without-removal"
            return original(*args, **kwargs)

        with (
            patch.object(custody, "docker", side_effect=incomplete),
            self.assertRaisesRegex(ValueError, "REMOVAL_UNCONFIRMED"),
        ):
            custody.cleanup_owned([item], self.operation)
        self.assertIn(item.cid, self.daemon.rows)

    def test_remove_timeout_observes_actual_absence_without_repeating_the_request(self):
        item = self.owned()
        self.launch(item)
        removed = []

        def interrupted(cid):
            removed.append(cid)
            del self.daemon.rows[cid]
            raise subprocess.TimeoutExpired("synthetic-docker", 1)

        self.daemon.before_remove = interrupted
        with self.assertRaises(subprocess.TimeoutExpired):
            custody.cleanup_owned([item], self.operation)
        self.assertEqual(removed, [item.cid])
        self.assertFalse(self.daemon.rows)
        self.assertTrue(
            any(args[:2] == ("container", "ls") and "id=" + item.cid in args for args, _ in self.daemon.calls)
        )

    def test_failed_inspection_or_inventory_never_means_container_absence(self):
        item = self.owned()
        self.launch(item)

        def refused(*args):
            raise ValueError("SYNTHETIC_DAEMON_UNAVAILABLE")

        for hook in ["before_inspect", "before_inventory"]:
            with self.subTest(hook=hook):
                setattr(self.daemon, hook, refused)
                with self.assertRaisesRegex(ValueError, "DAEMON_UNAVAILABLE"):
                    custody.cleanup_owned([item], self.operation)
                setattr(self.daemon, hook, None)
                self.assertFalse(self.daemon.removed)

    def test_failed_final_inventory_prevents_cleanup_confirmation(self):
        item = self.owned()
        self.launch(item)

        def arm(cid):
            def refused(expression):
                if expression == "id=" + cid:
                    raise ValueError("SYNTHETIC_FINAL_READ_FAILED")

            self.daemon.before_inventory = refused

        self.daemon.before_remove = arm
        with self.assertRaisesRegex(ValueError, "FINAL_READ_FAILED"):
            custody.cleanup_owned([item], self.operation)
        self.assertEqual(self.daemon.removed, [item.cid])

    def test_changed_image_labels_network_or_mounts_do_not_authorize_removal(self):
        item = self.owned()
        self.launch(item)
        original = copy.deepcopy(self.daemon.rows[item.cid])
        changes = {
            "image": lambda row: row.update(Image="sha256:" + "f" * 64),
            "operation": lambda row: row["Config"]["Labels"].update({custody.LABEL: str(uuid4())}),
            "role": lambda row: row["Config"]["Labels"].update({"org.onesa.rollback-role": "other"}),
            "user": lambda row: row["Config"].update(User="0:0"),
            "network": lambda row: row["HostConfig"].update(NetworkMode="host"),
            "extra-network": lambda row: row["NetworkSettings"]["Networks"].update(bridge={}),
            "bind-source": lambda row: row["Mounts"][0].update(Source="/foreign"),
            "bind-target": lambda row: row["Mounts"][0].update(Destination="/other"),
            "bind-rw": lambda row: row["Mounts"][0].update(RW=True),
            "extra-volume": lambda row: row["Mounts"].append(
                {"Type": "volume", "Destination": "/other", "RW": True}
            ),
            "tmpfs": lambda row: row["HostConfig"]["Tmpfs"].update({"/other": "rw"}),
            "privileged": lambda row: row["HostConfig"].update(Privileged=True),
            "command": lambda row: row["Config"].update(Cmd=["unrelated"]),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name):
                self.daemon.rows[item.cid] = copy.deepcopy(original)
                mutate(self.daemon.rows[item.cid])
                with self.assertRaises(ValueError):
                    custody.cleanup_owned([item], self.operation)
                self.assertFalse(self.daemon.removed)

    def test_same_name_replacement_cannot_inherit_a_created_cids_authority(self):
        item = self.owned()
        self.launch(item)
        replacement = self.daemon.rows.pop(item.cid)
        replacement["Id"] = "f" * 64
        self.daemon.rows[replacement["Id"]] = replacement
        with self.assertRaisesRegex(ValueError, "NAME_CID_MISMATCH"):
            custody.cleanup_owned([item], self.operation)
        self.assertFalse(self.daemon.removed)

    def test_unknown_operation_container_is_never_removed(self):
        item = self.owned()
        self.launch(item)
        foreign = copy.deepcopy(self.daemon.rows[item.cid])
        foreign.update(Id="f" * 64, Name="/foreign")
        self.daemon.rows[foreign["Id"]] = foreign
        with self.assertRaisesRegex(ValueError, "OPERATION_INVENTORY_CHANGED"):
            custody.cleanup_owned([item], self.operation)
        self.assertFalse(self.daemon.removed)

    def test_cid_value_or_inode_change_prevents_removal(self):
        item = self.owned()
        self.launch(item)
        item.cidfile.write_text("f" * 64)
        with self.assertRaisesRegex(ValueError, "CID_CHANGED"):
            custody.cleanup_owned([item], self.operation)
        item.cidfile.unlink()
        item.cidfile.write_text(item.cid + "\n")
        item.cidfile.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "CID_CHANGED"):
            custody.cleanup_owned([item], self.operation)
        self.assertFalse(self.daemon.removed)

    def test_hardlinked_cid_custody_is_refused(self):
        item = self.owned()
        self.launch(item)
        os.link(item.cidfile, item.cidfile.with_suffix(".alias"))
        with self.assertRaises(ValueError):
            custody.cleanup_owned([item], self.operation)
        self.assertFalse(self.daemon.removed)

    def test_malformed_duplicate_or_foreign_inventory_is_never_absence(self):
        for raw in [b"short-id\n", ("a" * 64 + "\n").encode() * 2, b"\xff"]:
            with (
                self.subTest(raw=raw),
                patch.object(custody, "docker", return_value=raw),
                self.assertRaises(ValueError),
            ):
                custody.inventory("id=" + "a" * 64)


if __name__ == "__main__":
    unittest.main()
