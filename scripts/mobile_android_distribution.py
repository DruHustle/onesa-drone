"""Build a private unsigned release and verify a separately owner-signed Drone APK."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import tempfile
import xml.etree.ElementTree as ET
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
    blocks = re.findall(r"-----BEGIN CERTIFICATE-----\s*([A-Za-z0-9+/=\s]+?)\s*-----END CERTIFICATE-----", report)
    native.require(len(blocks) == 1, "Expected precisely one release signer certificate")
    der = base64.b64decode("".join(blocks[0].split()), validate=True)
    native.require(hashlib.sha256(der).hexdigest() == expected, "Independent signer certificate pin differs")
    native.require(re.search(r"^Verified using v(?:2|3(?:\.1)?) scheme [^\n]+:\s*true\s*$", report, re.M)
                   and not re.search(r"certificate DN:.*\bAndroid Debug\b", report, re.I),
                   "Release APK signature scheme or signer identity differs")


BUNDLETOOL_SHA256 = "a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29"
ANDROID_ATTRIBUTE = "{http://schemas.android.com/apk/res/android}"


def bundle_manifest(xml, config):
    manifest = ET.fromstring(xml)
    app = manifest.find("application")
    sdk = manifest.find("uses-sdk")
    native.require(manifest.tag == "manifest" and manifest.get("package") == native.APP_ID
                   and app is not None and app.get(ANDROID_ATTRIBUTE + "debuggable", "false") == "false"
                   and app.get(ANDROID_ATTRIBUTE + "testOnly", "false") == "false" and sdk is not None,
                   "Expected a non-debuggable production Drone bundle")
    version = manifest.get(ANDROID_ATTRIBUTE + "versionName")
    code = int(manifest.get(ANDROID_ATTRIBUTE + "versionCode", "0"))
    minimum = int(sdk.get(ANDROID_ATTRIBUTE + "minSdkVersion", "0"))
    target = int(sdk.get(ANDROID_ATTRIBUTE + "targetSdkVersion", "0"))
    native.require(version == config["version"] and code == config["android"].get("versionCode", 1)
                   and code > 0 and 24 <= minimum <= target and 36 <= target <= 37,
                   "Unexpected version or SDK range in the release manifest")
    return {"package": native.APP_ID, "versionName": version, "versionCode": code,
            "minSdk": minimum, "targetSdk": target}


def bundle_contents(bundle, *, signed):
    native.require(bundle.is_file() and 0 < bundle.stat().st_size <= native.FILE_LIMIT, "Invalid bundle size")
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        names = set(archive.namelist())
        native.require(len(names) == len(entries) <= 32768
                       and sum(entry.file_size for entry in entries) <= native.BUNDLE_LIMIT,
                       "Invalid bundle entries")
        native.require({"BundleConfig.pb", "base/manifest/AndroidManifest.xml", "base/dex/classes.dex",
                        "base/assets/index.android.bundle", "base/lib/arm64-v8a/libreactnative.so"} <= names,
                       "Required Play bundle contents missing")
        signatures = [name.upper() for name in names if re.fullmatch(r"META-INF/[^/]+\.(SF|RSA|EC|DSA)", name, re.I)]
        if signed:
            native.require(len(signatures) == 2 and len({name.rsplit(".", 1)[0] for name in signatures}) == 1
                           and any(name.endswith(".SF") for name in signatures), "One upload signer required")
        else:
            native.require(not signatures, "Unsigned bundle unexpectedly contains a JAR signature")
        abis = {name.split("/")[2] for name in names if name.startswith("base/lib/") and name.endswith(".so")}
        native.require(abis == {"arm64-v8a"}, "Prepared bundle ABIs differ from the release target")
        excluded = {*signatures, "META-INF/MANIFEST.MF"}
        payload = []
        for name in sorted(names):
            if archive.getinfo(name).is_dir() or name.upper() in excluded:
                continue
            with archive.open(name) as member:
                payload.append([name, hashlib.file_digest(member, "sha256").hexdigest()])
    return hashlib.sha256(native.canonical(payload)).hexdigest()


def verify_play(directory, bundle, certificate):
    receipt = json.loads(native.regular_bytes(directory / "play-receipt.json", 64 * 1024))
    native.require(bundle_contents(bundle, signed=True) == receipt["payloadSha256"] ==
                   bundle_contents(directory / "OnesaDrone-unsigned.aab", signed=False),
                   "Signed bundle content differs from the prepared release")
    public_cert = ssl.PEM_cert_to_DER_cert(native.regular_bytes(certificate, 64 * 1024).decode().strip())
    pin = hashlib.sha256(public_cert).hexdigest()
    native.require(pin != native.BENCH_CERT_SHA256, "Bench signing key is ineligible for Play")
    # A trusted certificate entry lets strict verification check every signed
    # member against the owner's independently exported upload certificate.
    with tempfile.TemporaryDirectory() as tmp:
        trust = str(Path(tmp) / "upload-certificate.p12")
        env = {**os.environ, "DRONE_VERIFY_STORE_PASSWORD": secrets.token_urlsafe(24)}
        store = ["-keystore", trust, "-storetype", "PKCS12", "-storepass:env", "DRONE_VERIFY_STORE_PASSWORD"]
        subprocess.run(["keytool", "-importcert", "-noprompt", *store, "-alias", "upload",
                        "-file", str(certificate)], check=True, capture_output=True, env=env)
        subprocess.run(["jarsigner", "-verify", "-strict", *store, str(bundle), "upload"],
                       check=True, capture_output=True, env=env)
    return {**receipt, "signedBundleSha256": native.file_record(bundle)["sha256"],
            "uploadCertificateSha256": pin}


def build(directory, bundletool=None):
    directory = directory.resolve()
    native.require(not directory.is_relative_to(native.ROOT), "Use an output directory outside the checkout")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    if bundletool:
        native.require(native.file_record(bundletool)["sha256"] == BUNDLETOOL_SHA256,
                       "Use the pinned Google bundletool 1.18.3")
    native.prepare("android", directory / "source")
    mobile = native.ROOT / native.MOBILE_PATH
    init = directory / "unsigned.gradle"
    init.write_text(UNSIGNED)
    subprocess.run([str(mobile / "android/gradlew"), "-p", str(mobile / "android"), "-I", str(init),
                    ":app:assembleRelease", *([":app:bundleRelease"] if bundletool else []),
                    "-PreactNativeArchitectures=arm64-v8a", "--no-daemon", "--console=plain"],
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
    if bundletool:
        bundle = directory / "OnesaDrone-unsigned.aab"
        shutil.copyfile(mobile / "android/app/build/outputs/bundle/release/app-release.aab", bundle)
        bundle_arg = "--bundle=" + str(bundle)
        native.command("java", "-jar", str(bundletool), "validate", bundle_arg)
        manifest = native.command("java", "-jar", str(bundletool), "dump", "manifest", "--module=base", bundle_arg)
        checked = bundle_manifest(manifest, json.loads((mobile / "app.json").read_bytes())["expo"])
        play = {**checked, "sourceCommit": receipt["sourceCommit"], "architectures": ["arm64-v8a"],
                "unsignedBundleSha256": native.file_record(bundle)["sha256"],
                "payloadSha256": bundle_contents(bundle, signed=False)}
        (directory / "play-receipt.json").write_bytes(native.canonical(play) + b"\n")
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
    verify_signer(native.command(sdk_tool("apksigner"), "verify", "--verbose", "--print-certs-pem", str(apk)), certificate)
    version = expected["versionName"]
    filename = "onesa-drone-android-v" + version + ".apk"
    native.require(url in {"https://github.com/DruHustle/onesa-drone/releases/download/mobile-v" + version + "/" + filename,
                           "https://drone.onesa.eu/downloads/" + filename}, "Unexpected versioned release destination")
    return {"url": url, "sha256": native.file_record(apk)["sha256"],
            "certificateSha256": certificate, "sourceCommit": receipt["sourceCommit"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("build")
    prepare.add_argument("--directory", required=True, type=Path)
    prepare.add_argument("--bundletool", type=Path, help="Also prepare and verify a Play release AAB")
    play = sub.add_parser("verify-play", help="Verify the owner-signed application bundle")
    play.add_argument("--directory", required=True, type=Path)
    play.add_argument("--aab", required=True, type=Path)
    play.add_argument("--upload-certificate", required=True, type=Path, help="Trusted public X.509 PEM")

    review = sub.add_parser("verify")
    review.add_argument("--directory", required=True, type=Path)
    review.add_argument("--apk", required=True, type=Path)
    review.add_argument("--certificate-sha256", required=True)
    review.add_argument("--url", required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build(args.directory, args.bundletool.resolve() if args.bundletool else None)
    elif args.command == "verify-play":
        result = verify_play(args.directory, args.aab, args.upload_certificate)
    else:
        result = verify(args.directory, args.apk, args.certificate_sha256.lower(), args.url)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
