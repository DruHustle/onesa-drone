"""Qualify an unsigned device archive without a distribution key or device access."""

import argparse
import json
from pathlib import Path
import plistlib
import re
import subprocess

from scripts import mobile_native_compile as native


def check(archive):
    archive_info = plistlib.loads(native.regular_bytes(archive / "Info.plist", 1024 * 1024))
    properties = archive_info.get("ApplicationProperties", {})
    native.require(properties.get("ApplicationPath") == "Applications/OnesaDrone.app", "Unexpected device archive layout")
    app = archive / "Products/Applications/OnesaDrone.app"
    info = plistlib.loads(native.regular_bytes(app / "Info.plist", 1024 * 1024))
    native.require(info.get("CFBundleIdentifier") == native.APP_ID and info.get("CFBundleExecutable") == native.APP_NAME
                   and info.get("CFBundleSupportedPlatforms") == ["iPhoneOS"] and info.get("DTPlatformName") == "iphoneos"
                   and set(info.get("UIDeviceFamily", [])) == {1, 2}, "Expected the Drone iPhone/iPad device application")
    config = json.loads((native.ROOT / native.MOBILE_PATH / "app.json").read_text())["expo"]
    sdk = re.fullmatch(r"iphoneos(\d+)(?:\.\d+)*", info.get("DTSDKName", ""))
    native.require(sdk and int(sdk[1]) >= 26, "App Store submission requires the iOS 26 SDK or later")
    native.require(info.get("CFBundleVersion") == config["ios"]["buildNumber"]
                   and info.get("CFBundleShortVersionString") == config["version"],
                   "Archive version differs from the release configuration")
    schemes = {scheme for entry in info.get("CFBundleURLTypes", []) for scheme in entry.get("CFBundleURLSchemes", [])}
    native.require(config["scheme"] in schemes, "Native sign-in callback is missing from the archive")
    native.require(info.get("CFBundleIcons", {}).get("CFBundlePrimaryIcon", {}).get("CFBundleIconName")
                   and (app / "Assets.car").is_file(), "Compiled App Store icon is missing")
    native.require(not (app / "embedded.mobileprovision").exists() and not (app / "_CodeSignature").exists(),
                   "An unsigned archive must not carry a provisioning profile or application signature seal")
    executable = app / native.APP_NAME
    native.require(native.command("xcrun", "lipo", "-archs", str(executable)) == "arm64", "Expected an arm64 device binary")
    platforms = re.findall(r"^\s*platform\s+(\S+)\s*$", native.command("xcrun", "vtool", "-show-build", str(executable)), re.M)
    native.require(platforms == ["IOS"], "Mach-O platform must be iOS device")
    signature = subprocess.run(["/usr/bin/codesign", "--display", "--verbose=4", str(executable)],
                               capture_output=True, text=True, timeout=30)
    details = signature.stderr + signature.stdout
    if signature.returncode == 0:
        native.require(re.search(r"^Signature=adhoc$", details, re.M)
                       and not re.search(r"^Authority=", details, re.M)
                       and "TeamIdentifier=not set" in details, "Unexpected distribution signature")
    else:
        native.require("not signed at all" in details, "Could not determine executable signing state")
    bundle = native.file_record(app / "main.jsbundle")
    return {"application_id": native.APP_ID, "version": info["CFBundleShortVersionString"], "build": info["CFBundleVersion"],
            "sdk": info["DTSDKName"], "architecture": "arm64", "configuration": "Release", "target": "iphoneos",
            "embedded_bundle": bundle, "executable": native.file_record(executable), "distribution_signed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.archive), sort_keys=True))
