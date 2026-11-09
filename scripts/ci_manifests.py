"""Credential-free component provenance; output contains only hashes and public build metadata."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def source_binding(root=ROOT):
    """Bind the actual Git repository and product subtree, never a legacy label."""
    root = root.resolve()
    checkout = Path(command("git", "-C", str(root), "rev-parse", "--show-toplevel")).resolve()
    path = root.relative_to(checkout).as_posix()
    if path == ".":
        repository = "DruHustle/onesa-drone"
    elif path == "onesa-drone":
        repository = "DruHustle/onesa-ug"
    else:
        raise SystemExit("Unrecognized Drone source location")
    origin = command("git", "-C", str(root), "remote", "get-url", "origin")
    if origin not in {
        f"https://github.com/{repository}",
        f"https://github.com/{repository}.git",
        f"git@github.com:{repository}.git",
        f"ssh://git@github.com/{repository}.git",
    } or os.environ.get("GITHUB_REPOSITORY", repository) != repository:
        raise SystemExit("Drone source repository differs from its checked location")
    if command("git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--", "."):
        raise SystemExit("Drone source contains uncommitted changes")
    commit = command("git", "-C", str(root), "rev-parse", "HEAD")
    value = {
        "repository": repository,
        "source_commit": commit,
        "source_tree": command("git", "-C", str(root), "rev-parse", "HEAD^{tree}"),
    }
    if path != ".":
        value["source_path"] = path
        value["product_source_tree"] = command("git", "-C", str(root), "rev-parse", f"HEAD:{path}")
        # Build provenance remains non-authorizing. Only the separately installed
        # canonical owner consumer can bind it to hosted release qualification.
        value["verification_only"] = True
        value["release_authorized"] = False
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--image-archive", type=Path, required=True)
    args = parser.parse_args()
    source = source_binding()
    commit = source["source_commit"]
    args.output.mkdir(parents=True, exist_ok=False)
    for component in ["backend", "frontend"]:
        value = {
            **source,
            "component": component,
            "mode": "simulation",
        }
        if component == "backend":
            # Docker's containerd and classic stores expose different top-level IDs.
            # Bind the portable image configuration bytes from the scanned archive.
            with tarfile.open(args.image_archive) as archive:
                manifest = json.load(archive.extractfile("manifest.json"))
                if len(manifest) != 1:
                    raise SystemExit("Exactly one runtime image is required")
                config = archive.extractfile(manifest[0]["Config"]).read()
            value["image_id"] = "sha256:" + hashlib.sha256(config).hexdigest()
            value["runtime_image_id"] = command(
                "docker", "image", "inspect", "--format", "{{.Id}}", args.image
            )
            value["architecture"] = command(
                "docker", "image", "inspect", "--format", "{{.Architecture}}", args.image
            )
            label = command(
                "docker",
                "image",
                "inspect",
                "--format",
                '{{index .Config.Labels "org.onesa.source-commit"}}',
                args.image,
            )
            if label != commit:
                raise SystemExit("Runtime image source label differs from checked source")
        else:
            dist = ROOT / "frontend/dist"
            files = {
                str(p.relative_to(dist)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(dist.rglob("*"))
                if p.is_file()
            }
            if "index.html" not in files:
                raise SystemExit("Frontend build missing")
            value["files"] = files
        (args.output / (component + ".json")).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
