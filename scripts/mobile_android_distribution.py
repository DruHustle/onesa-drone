"""Build a private unsigned release and verify a separately owner-signed Drone APK."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from scripts import mobile_native_compile as native

# AGP calls finalizeDsl after project DSL configuration, before it creates variants.
# Expo templates can otherwise select the development key for their release variant.
UNSIGNED = """gradle.beforeProject { project ->
    project.plugins.withId('com.android.application') {
        project.extensions.getByName('androidComponents').finalizeDsl { android ->
            android.buildTypes.getByName('release').signingConfig = null
        }
    }
}
"""


def sdk_tool(name):
    return str(Path(os.environ["ANDROID_HOME"]) / "build-tools/37.0.0" / name)


def payload_hash(apk):
    """v2/v3 signatures live outside ZIP members; compare all member names and bytes."""
    native.require(apk.is_file() and 0 < apk.stat().st_size <= native.FILE_LIMIT, "Invalid APK size")
    with zipfile.ZipFile(apk) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        native.require(0 < len(entries) <= 8192 and len(set(names)) == len(names)
                       and sum(entry.file_size for entry in entries) <= native.BUNDLE_LIMIT, "Invalid APK members")
        native.require({"AndroidManifest.xml", "classes.dex", "assets/index.android.bundle",
                        "lib/arm64-v8a/libreactnative.so"}.issubset(names), "Embedded release bundle is incomplete")
        records = []
        for name in sorted(names):
            with archive.open(name) as stream:
                records.append([name, hashlib.file_digest(stream, "sha256").hexdigest()])
    return hashlib.sha256(native.canonical(records)).hexdigest()


def release_version(badging):
    match = re.search(r"^package: name='eu\.onesa\.drone' versionCode='([1-9][0-9]*)' versionName='([0-9]+\.[0-9]+\.[0-9]+)'", badging, re.M)
    native.require(match and not re.search(r"^application-debuggable\s*$", badging, re.M),
                   "A non-debuggable eu.onesa.drone release is required")
    return {"versionCode": int(match[1]), "versionName": match[2]}


def verify_signer(report, expected):
    native.require(re.fullmatch(r"[0-9a-f]{64}", expected), "Independent release certificate SHA-256 required")
    certs = re.findall(r"^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$", report, re.M)
    native.require([item.lower() for item in certs] == [expected]
                   and re.search(r"^Verified using v[23] scheme .*: true$", report, re.M)
                   and not re.search(r"certificate DN:.*\bAndroid Debug\b", report, re.I),
                   "Release signer or APK signature scheme differs")


def build(directory):
    directory = directory.resolve()
    native.require(not directory.is_relative_to(native.ROOT), "Use an output directory outside the checkout")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    native.prepare("android", directory / "source")
    mobile = native.ROOT / native.MOBILE_PATH
    init = directory / "unsigned.gradle"
    init.write_text(UNSIGNED)
    subprocess.run([str(mobile / "android/gradlew"), "-p", str(mobile / "android"), "-I", str(init),
                    ":app:assembleRelease", "-PreactNativeArchitectures=arm64-v8a", "--no-daemon", "--console=plain"],
                   cwd=mobile, check=True, env={**os.environ, "NODE_ENV": "production", "EXPO_NO_TELEMETRY": "1"})
    apk = mobile / "android/app/build/outputs/apk/release/app-release-unsigned.apk"
    native.require(apk.is_file(), "Expected the unsigned release build output")
    aligned = directory / "aligned-unsigned.apk"
    subprocess.run([sdk_tool("zipalign"), "-P", "16", "4", str(apk), str(aligned)], check=True)
    signature = subprocess.run([sdk_tool("apksigner"), "verify", str(aligned)], capture_output=True)
    native.require(signature.returncode != 0, "The release preparation unexpectedly selected a signing key")
    version = release_version(native.command(sdk_tool("aapt"), "dump", "badging", str(aligned)))
    prepared = json.loads((directory / "source/prepared.json").read_bytes())
    native.source_unchanged(native.ROOT, prepared["source"], "android")
    native.require(prepared["inputs"] == native.locked_inputs(mobile), "Locked native inputs changed")
    receipt = {"sourceCommit": prepared["source"]["source_commit"], "payloadSha256": payload_hash(aligned), **version}
    (directory / "unsigned-receipt.json").write_bytes(native.canonical(receipt) + b"\n")
    return receipt


def verify(directory, apk, certificate, url):
    receipt = json.loads(native.regular_bytes(directory / "unsigned-receipt.json", 64 * 1024))
    apk = apk.resolve()
    expected = release_version(native.command(sdk_tool("aapt"), "dump", "badging", str(apk)))
    native.require(all(receipt[k] == value for k, value in expected.items()), "Signed release version differs")
    native.require(re.fullmatch(r"[a-f0-9]{40}", receipt["sourceCommit"])
                   and payload_hash(apk) == receipt["payloadSha256"]
                   and payload_hash(directory / "aligned-unsigned.apk") == receipt["payloadSha256"],
                   "Signed payload differs from the prepared build")
    native.command(sdk_tool("zipalign"), "-c", "-P", "16", "4", str(apk))
    verify_signer(native.command(sdk_tool("apksigner"), "verify", "--verbose", "--print-certs", str(apk)), certificate)
    version = expected["versionName"]
    filename = "onesa-drone-android-v" + version + ".apk"
    native.require(url in {"https://github.com/DruHustle/onesa-drone/releases/download/mobile-v" + version + "/" + filename,
                           "https://drone.onesa.eu/downloads/" + filename}, "Unexpected versioned release destination")
    return {"url": url, "sha256": native.file_record(apk)["sha256"],
            "certificateSha256": certificate, "sourceCommit": receipt["sourceCommit"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build").add_argument("--directory", required=True, type=Path)
    review = sub.add_parser("verify")
    review.add_argument("--directory", required=True, type=Path)
    review.add_argument("--apk", required=True, type=Path)
    review.add_argument("--certificate-sha256", required=True)
    review.add_argument("--url", required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build(args.directory)
    else:
        result = verify(args.directory, args.apk, args.certificate_sha256.lower(), args.url)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
