"""Credential-free component provenance; output contains only hashes and public build metadata."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--image-archive", type=Path, required=True)
    args = parser.parse_args()
    commit = command("git", "rev-parse", "HEAD")
    tree = command("git", "rev-parse", "HEAD^{tree}")
    args.output.mkdir(parents=True, exist_ok=False)
    for component in ["backend", "frontend"]:
        value = {
            "repository": "DruHustle/onesa-drone",
            "component": component,
            "source_commit": commit,
            "source_tree": tree,
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
            dist = Path("frontend/dist")
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
