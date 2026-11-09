"""Install exact-main Drone release tools without commissioning release authority.

Use an independently hash-checked copy over the existing owner SSH/sudo route.
Every executable must equal its current canonical Git blob, and bounded source
artifacts must pass the existing full source/CI verifier. This installer writes
only a new immutable directory; existing keys, stores and runtime plans remain in
their original custody. Bootstrap and commissioning are separate owner actions.
"""

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle_owner as owner

INSTALL_PARENT = Path("/usr/local/lib/onesa-release")
ALLOWED = {
    "oracle_owner.py": "scripts/release/oracle_owner.py",
    "oracle_install.py": "scripts/release/oracle_install.py",
    "runners/oracle_drone.py": "scripts/release/oracle_drone.py",
    "runners/oracle_drone_identity.py": "scripts/release/oracle_drone_identity.py",
    "runners/oracle_drone_rollback.py": "scripts/release/oracle_drone_rollback.py",
    "runners/oracle_drone_rollback_containers.py": "scripts/release/oracle_drone_rollback_containers.py",
    "runners/oracle_drone_identity_browser.mjs": "scripts/release/oracle_drone_identity_browser.mjs",
    "runners/probe_policy.mjs": "scripts/release/probe_policy.mjs",
    "runners/hosted_probe.mjs": "scripts/release/hosted_probe.mjs",
    "runners/vercel_transport_guard.cjs": "scripts/release/vercel_transport_guard.cjs",
}


def checked(path, pin, uid, *, limit=2 * 1024 * 1024):
    path = Path(path)
    owner.private(path, uid=uid)
    owner.require(isinstance(pin, str) and owner.HEX.fullmatch(pin)
                  and 0 < path.stat().st_size <= limit, "Bounded pinned installation file required")
    data = path.read_bytes()
    owner.require(hashlib.sha256(data).hexdigest() == pin, "Installation bytes changed")
    return data


def relative(name):
    path = PurePosixPath(name)
    owner.require(not path.is_absolute() and str(path) == name
                  and all(part not in {"", ".", ".."} for part in path.parts), "Installation path refused")
    return path


def validate(bundle, manifest_pin, github, *, uid=0):
    bundle = Path(bundle)
    owner.private(bundle, directory=True, uid=uid)
    manifest = owner.source_json(checked(bundle / "manifest.json", manifest_pin, uid))
    owner.require(isinstance(manifest, dict) and set(manifest) == owner.DRONE_SOURCE_FIELDS | {
        "files", "policy_sha256", "tool_source_sha256",
    }, "Canonical Drone installation manifest required")
    source = owner.drone_operational_source(manifest)
    owner.require(isinstance(manifest["files"], dict) and set(manifest["files"]) == set(ALLOWED),
                  "Exact reviewed Drone installation files required")
    owner.require(manifest["files"]["oracle_owner.py"] == owner.file_digest(owner.__file__)
                  and manifest["files"]["oracle_install.py"] == owner.file_digest(__file__),
                  "Invoked bootstrap code differs from installation source")
    policy_bytes = checked(bundle / "policy.json", manifest["policy_sha256"], uid)
    policy = owner.source_json(policy_bytes)
    owner.require(isinstance(policy, dict) and set(policy) == {"schema_version", "components", "toolchain"}
                  and type(policy["schema_version"]) is int and policy["schema_version"] == 2,
                  "Canonical Drone installation policy required")
    tool = policy["toolchain"]
    owner.require(isinstance(tool, dict) and set(tool) == {
        "source_commit", "source_tree", "source_sha256", "source_binding", "source_archives", "files",
    } and tool["source_binding"] == source and tool["source_commit"] == source["candidate_commit"]
        and tool["source_tree"] == source["source_tree"]
        and tool["source_sha256"] == manifest["tool_source_sha256"]
        and tool["files"] == manifest["files"], "Canonical Drone toolchain source differs")
    archives = owner.drone_source_archives(
        bundle / "source-artifacts", owner.drone_archive_pins(tool), uid=uid,
    )
    github.owner()
    ci = github.qualify(source, archives)
    owner.require(ci, "Fresh exact-main source evidence required")
    tree = github.api("repos/" + source["repository"] + "/git/trees/"
                      + source["product_source_tree"] + "?recursive=1")
    owner.require(tree.get("sha") == source["product_source_tree"]
                  and tree.get("truncated") is False and isinstance(tree.get("tree"), list),
                  "Complete exact Drone source tree required")
    rows = tree["tree"]
    owner.require(len(rows) < 20000 and len({row["path"] for row in rows}) == len(rows),
                  "Unambiguous Drone source tree required")
    blobs = {row["path"]: row for row in rows if row["type"] == "blob"}
    payloads = {"source-artifacts/" + name + ".zip": base64.b64decode(data, validate=True)
                for name, data in archives.items()}
    for local, upstream in ALLOWED.items():
        data = checked(bundle / relative(local), manifest["files"][local], uid)
        blob = blobs.get(upstream)
        owner.require(blob and blob["mode"] == "100644", "Reviewed executable Git blob required")
        observed = github.api("repos/" + source["repository"] + "/git/blobs/" + blob["sha"])
        owner.require(observed.get("sha") == blob["sha"] and observed.get("encoding") == "base64"
                      and base64.b64decode(observed["content"], validate=False) == data,
                      "Installation executable differs from current canonical source")
        payloads[local] = data
    archive = checked(bundle / "tool-source.tar", manifest["tool_source_sha256"], uid,
                      limit=128 * 1024 * 1024)
    files = owner.source_inventory(bundle / "tool-source.tar", source)
    owner.require(all(files.get(upstream) == manifest["files"][local] for local, upstream in ALLOWED.items()),
                  "Product archive executable identities differ")
    target = INSTALL_PARENT / ("drone-canonical-" + source["source_tree"])
    owner.require(set(policy["components"]) == {
        owner.CONSOLIDATED_REPOSITORY + ":drone:" + component for component in owner.DRONE_COMPONENTS
    }, "The complete canonical backend/frontend profile pair is required")
    for component in sorted(owner.DRONE_COMPONENTS):
        binding = {
            **source, "component": component, "source_sha256": manifest["tool_source_sha256"],
            "build_sha256": "0" * 64, "artifact_digest": "sha256:" + "0" * 64,
            "configuration_sha256": {"staging": "0" * 64, "production": "0" * 64},
            "target_environment": "production",
        }
        profile = owner.binding_valid(binding, policy)
        for runner in profile["runners"].values():
            owner.require(runner["path"] == str(target / "runners/oracle_drone.py")
                          and runner["sha256"] == manifest["files"]["runners/oracle_drone.py"],
                          "Phase runner differs from immutable reviewed installation")
    payloads.update({"policy.json": policy_bytes, "tool-source.tar": archive})
    return manifest, target, payloads, ci


def install(bundle, manifest_pin, github, *, dry_run=False, uid=0):
    manifest, target, payloads, ci = validate(bundle, manifest_pin, github, uid=uid)
    owner.require(not target.exists() and not target.is_symlink(),
                  "Existing immutable installation retained; inspect instead of overwriting")
    if dry_run:
        return {"state": "INSTALLATION_READY", "target": str(target),
                "source_binding": owner.drone_operational_source(manifest),
                "provider_requests": 0, "release_authorized": False, "ci": ci}
    owner.require(uid == 0 and os.geteuid() == 0 and os.getenv("SUDO_USER") == "ubuntu"
                  and not os.getenv("GITHUB_ACTIONS"), "Existing owner SSH/sudo installation required")
    if not INSTALL_PARENT.exists():
        owner.require(all(not path.is_symlink() and path.stat().st_uid == 0 and path.stat().st_mode & 0o022 == 0
                          for path in [INSTALL_PARENT.parent, *INSTALL_PARENT.parent.parents]),
                      "Untrusted installation parent")
        INSTALL_PARENT.mkdir(mode=0o700)
    owner.private(INSTALL_PARENT, directory=True)
    target.mkdir(mode=0o700)
    try:
        (target / "runners").mkdir(mode=0o700)
        (target / "source-artifacts").mkdir(mode=0o700)
        for name, data in payloads.items():
            with os.fdopen(os.open(target / relative(name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        receipt = {
            "state": "INSTALLED_NOT_COMMISSIONED", "repository": manifest["repository"],
            "source": manifest["candidate_commit"], "source_tree": manifest["source_tree"],
            "source_binding": owner.drone_operational_source(manifest), "files": manifest["files"],
            "policy_sha256": manifest["policy_sha256"], "ci": ci, "provider_requests": 0,
            "release_authorized": False,
        }
        with os.fdopen(os.open(target / "installation.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
            stream.write(owner.canonical(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        for directory in [target / "runners", target / "source-artifacts", target, INSTALL_PARENT]:
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return {**receipt, "target": str(target)}
    except BaseException:
        raise owner.Rejected("Installation interrupted; retain and inspect immutable version; no automatic retry") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-pin", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    owner.require(os.geteuid() == 0 and os.getenv("SUDO_USER") == "ubuntu"
                  and not os.getenv("GITHUB_ACTIONS"), "Existing owner SSH/sudo installation required")
    raw = sys.stdin.buffer.read(64 * 1024 + 1)
    owner.require(len(raw) <= 64 * 1024, "Private installer request bound")
    request = owner.source_json(raw)
    owner.require(isinstance(request, dict) and set(request) == {"owner_token"}, "Exact owner custody input required")
    result = install(args.bundle, args.manifest_pin, owner.GitHub(request["owner_token"]), dry_run=args.dry_run)
    print(owner.canonical(result).decode())


if __name__ == "__main__":
    main()
