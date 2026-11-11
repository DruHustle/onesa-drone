"""Prepare and qualify native verification builds and offline Android bench packages."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile

from scripts.ci_manifests import source_binding


ROOT = Path(__file__).resolve().parents[1]
MOBILE_PATH = Path("frontend/drone/mobile")
EXPO_VERSION = "58.0.23"
TEMPLATE_SHA256 = "fd276079c5e909c66499ec9de19f91638909d4fb3eff8fa4afa2824aac249f11"
GRADLE_VERSION = "9.4.1"
GRADLE_NETWORK_TIMEOUT_MS = 60000
# https://services.gradle.org/distributions/gradle-9.4.1-bin.zip.sha256
GRADLE_SHA256 = "2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb"
ANDROID_VERSIONS = {"compileSdk": "37", "buildTools": "37.0.0", "ndkVersion": "27.1.12297006"}
FILE_LIMIT = 256 * 1024 * 1024
BUNDLE_LIMIT = 512 * 1024 * 1024
APP_ID = "eu.onesa.drone"
APP_NAME = "OnesaDrone"
BENCH_APP_ID = APP_ID + ".bench"
BENCH_LABEL = "Onesa Drone Bench"
# SHA-256 of the DER certificate in the locked Expo template's android/app/debug.keystore.
BENCH_CERT_SHA256 = "fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c"
HERMES_VERSION = 99  # Bytecode emitted by the locked hermes-compiler package.
HERMES_MAGIC = bytes.fromhex("c61fbc03c103191f")


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def regular_bytes(path, limit, *, allow_empty=False):
    mode = path.lstat()
    require(stat.S_ISREG(mode.st_mode) and (0 if allow_empty else 1) <= mode.st_size <= limit,
            "Expected bounded regular file")
    data = path.read_bytes()
    require(len(data) == mode.st_size, "File changed while reading")
    return data


def file_record(path, limit=FILE_LIMIT, *, allow_empty=False):
    data = regular_bytes(path, limit, allow_empty=allow_empty)
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def command(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True, timeout=120)
    require(len(result.stdout) <= 64 * 1024, "Unexpected toolchain output")
    return result.stdout.strip()


def locked_inputs(mobile):
    inputs = {}
    records = {}
    for name in ("package.json", "package-lock.json", "app.json"):
        data = regular_bytes(mobile / name, 2 * 1024 * 1024)
        inputs[name] = hashlib.sha256(data).hexdigest()
        records[name] = json.loads(data)
    package, lock, config = (records[name] for name in ("package.json", "package-lock.json", "app.json"))
    dependencies = package["dependencies"]
    require(lock["lockfileVersion"] == 3 and lock["packages"][""]["dependencies"] == dependencies,
            "Mobile dependency lock differs")
    require(dependencies.get("expo") == EXPO_VERSION and dependencies.get("react-native") == "0.88.1",
            "Native toolchain requires an explicit reviewed SDK update")
    for name, version in dependencies.items():
        require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "Exact mobile dependency version required")
        installed = json.loads(regular_bytes(mobile / "node_modules" / name / "package.json", 512 * 1024))
        require(installed["version"] == version and lock["packages"]["node_modules/" + name]["version"] == version,
                "Installed mobile dependency differs from its lock")
    expo = config["expo"]
    require(expo["name"] == "Onesa Drone" and expo["ios"]["bundleIdentifier"] == APP_ID
            and expo["android"]["package"] == APP_ID and expo["ios"]["supportsTablet"] is True
            and expo["userInterfaceStyle"] == "automatic" and expo["updates"]["enabled"] is False
            and expo["extra"]["hardwareFlightEnabled"] is False and expo["extra"]["simulationOnly"] is True,
            "Native compilation requires the reviewed simulation-only app configuration")
    template = mobile / "node_modules/expo/template.tgz"
    require(file_record(template, 1024 * 1024)["sha256"] == TEMPLATE_SHA256, "Locked Expo template differs")
    versions = tomllib.loads(regular_bytes(
        mobile / "node_modules/react-native/gradle/libs.versions.toml", 64 * 1024,
    ).decode())["versions"]
    require(all(versions[key] == value for key, value in ANDROID_VERSIONS.items()),
            "Pinned React Native Android toolchain differs")
    return {"files_sha256": inputs, "dependencies": dependencies, "expo_template_sha256": TEMPLATE_SHA256}


def pin_gradle_wrapper(wrapper):
    text = regular_bytes(wrapper, 16 * 1024).decode()
    expected = "distributionUrl=https\\://services.gradle.org/distributions/gradle-" + GRADLE_VERSION + "-bin.zip"
    require(text.splitlines().count(expected) == 1 and "distributionSha256Sum=" not in text,
            "Generated Gradle distribution differs")
    timeouts = [line for line in text.splitlines() if line.startswith("networkTimeout=")]
    require(timeouts == ["networkTimeout=10000"], "Generated Gradle network timeout differs")
    text = text.replace("networkTimeout=10000", "networkTimeout=" + str(GRADLE_NETWORK_TIMEOUT_MS))
    wrapper.write_text(text.rstrip() + "\ndistributionSha256Sum=" + GRADLE_SHA256 + "\n")


def configure_bench(native):
    # Only change generated native inputs. Keep the Java namespace, entry activity,
    # locked Expo bundler and the template's test-signing configuration intact.
    for path, old, new in [
        (native / "app/build.gradle", f"applicationId '{APP_ID}'", f"applicationId '{BENCH_APP_ID}'"),
        (native / "app/src/main/res/values/strings.xml", '<string name="app_name">Onesa Drone</string>',
         f'<string name="app_name">{BENCH_LABEL}</string>'),
    ]:
        data = regular_bytes(path, 128 * 1024).decode()
        require(data.count(old) == 1, "Generated Android application configuration differs")
        path.write_text(data.replace(old, new))


def prepare(platform, output, root=ROOT, *, bench=False):
    require(not bench or platform == "android", "Bench builds require Android")
    mobile = root / MOBILE_PATH
    inputs = locked_inputs(mobile)
    source = source_binding(root)
    require(os.environ.get("GITHUB_SHA", source["source_commit"]) == source["source_commit"],
            "Native checkout differs from the workflow source")
    native = mobile / platform
    require(not native.is_symlink() and native.is_dir()
            and {entry.name for entry in native.iterdir()} == {"README.md"}
            and (native / "README.md").is_file() and not (native / "README.md").is_symlink(),
            "Native generation may replace only the tracked placeholder directory")
    output.mkdir(parents=True, exist_ok=False)
    subprocess.run([
        "node", "node_modules/expo/bin/cli", "prebuild", "--platform", platform, "--no-install",
        "--template", "./node_modules/expo/template.tgz", "--clean",
    ], cwd=mobile, env={**os.environ, "CI": "1", "EXPO_NO_TELEMETRY": "1"}, check=True)
    require(locked_inputs(mobile) == inputs, "Native generation changed locked application inputs")
    if platform == "android":
        pin_gradle_wrapper(native / "gradle/wrapper/gradle-wrapper.properties")
        if bench:
            configure_bench(native)
    else:
        require((native / (APP_NAME + ".xcodeproj/project.pbxproj")).is_file(),
                "Generated iOS target differs")
    prepared = {"platform": platform, "source": source, "inputs": inputs}
    if bench:
        prepared["variant"] = "bench"
    (output / "prepared.json").write_bytes(canonical(prepared) + b"\n")


def embedded_hermes(archive):
    path = "assets/index.android.bundle"
    require(path in archive.namelist(), "Offline Hermes bundle missing")
    info = archive.getinfo(path)
    require(128 < info.file_size <= 64 * 1024 * 1024, "Offline Hermes bundle size differs")
    data = archive.read(info)
    require(data[:8] == HERMES_MAGIC and struct.unpack_from("<I", data, 8)[0] == HERMES_VERSION
            and struct.unpack_from("<I", data, 32)[0] == len(data)
            and hashlib.sha1(data[:-20]).digest() == data[-20:], "Offline Hermes bytecode differs")
    return {"name": path, "bytecode_version": HERMES_VERSION, "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def bench_signer(verification):
    counts = re.findall(r"^Number of signers: ([0-9]+)$", verification, re.M)
    schemes = re.findall(r"^Verified using v(2|3(?:\.[12])?) scheme [^\n]+: true$", verification, re.M)
    certs = re.findall(r"^(.+?) certificate SHA-256 digest: (.*)$", verification, re.M)
    # Build-tools 37 names the signature scheme in the signer label. Each SDK
    # range may also list the same certificate. Check every reported certificate.
    label = r"(?:V(?:2|3(?:\.[012])?) Signer:|Signer #1|Signer \(minSdkVersion=\d+, maxSdkVersion=\d+\):?)"
    all_labels_known = all(re.fullmatch(label, prefix) for prefix, _ in certs)
    digests = {digest.lower() for _, digest in certs}
    matches = digests == {BENCH_CERT_SHA256}
    require(counts == ["1"] and schemes and matches and all_labels_known,
            "Expected the reviewed Expo test signing certificate and modern APK signature "
            f"(signer count: {','.join(counts) or 'unreported'}, verified schemes: "
            f"{','.join(schemes) or 'none'}, certificate entries: {len(certs)}, "
            f"all labels recognized: {all_labels_known}, certificate pin matches: {matches})")
    return {"code_signature": "expo-template-test-key", "signer_certificate_sha256": BENCH_CERT_SHA256,
            "distribution_signed": False}


def android_identity(apk, badging, *, bench=False):
    app_id = BENCH_APP_ID if bench else APP_ID
    debuggable = bool(re.search(r"^application-debuggable\s*$", badging, re.M))
    require(re.search(r"^package: name='" + re.escape(app_id) + r"' ", badging, re.M)
            and debuggable == (not bench), "Expected the Drone Android application identity")
    identity = {"application_id": app_id, "architecture": "arm64-v8a",
                "configuration": "release" if bench else "debug"}
    if bench:
        require(f"application-label:'{BENCH_LABEL}'" in badging.splitlines()
                and re.search(r"^launchable-activity: name='eu\.onesa\.drone\.MainActivity' ", badging, re.M),
                "Expected the bench label and launch activity")
    with zipfile.ZipFile(apk) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        require(0 < len(entries) <= 8192 and len(set(names)) == len(names)
                and sum(item.file_size for item in entries) <= BUNDLE_LIMIT, "APK contents exceed bounds")
        for item in entries:
            parts = item.filename.rstrip("/").split("/")
            require(not item.flag_bits & 1 and not item.filename.startswith("/")
                    and "\\" not in item.filename and all(part not in {"", ".", ".."} for part in parts)
                    and stat.S_IFMT(item.external_attr >> 16) in {0, stat.S_IFREG, stat.S_IFDIR},
                    "Unexpected APK member")
        require("AndroidManifest.xml" in names and "classes.dex" in names,
                "Android application payload missing")
        with archive.open("classes.dex") as stream:
            require(stream.read(4) == b"dex\n", "Android DEX payload missing")
        native = archive.getinfo("lib/arm64-v8a/libreactnative.so")
        require(64 <= native.file_size <= FILE_LIMIT, "Android React Native library missing")
        with archive.open(native) as stream:
            header = stream.read(64)
        require(header[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", header, 18)[0] == 183,
                "Android native payload is not arm64 ELF")
        require(not any(name.startswith("lib/") and not name.endswith("/")
                        and not name.startswith("lib/arm64-v8a/") for name in names),
                "Unexpected Android native architecture")
        if bench:
            identity["embedded_bundle"] = embedded_hermes(archive)
    return identity


def adhoc_signature(data):
    """Allow only a bounded ad-hoc CodeDirectory, with no CMS signer blob."""
    require(len(data) >= 12, "Simulator code signature is truncated")
    magic, length, count = struct.unpack_from(">3I", data)
    require(magic == 0xFADE0CC0 and 12 <= length <= len(data) and 1 <= count <= 32
            and 12 + count * 8 <= length, "Simulator code signature is malformed")
    directories = 0
    slots = set()
    for index in range(count):
        slot, offset = struct.unpack_from(">2I", data, 12 + index * 8)
        require(slot not in slots and 12 + count * 8 <= offset <= length - 8,
                "Simulator code signature slot differs")
        slots.add(slot)
        kind, size = struct.unpack_from(">2I", data, offset)
        require(8 <= size <= length - offset, "Simulator code signature blob is truncated")
        if slot == 0 or 0x1000 <= slot <= 0x1005:
            require(kind == 0xFADE0C02 and size >= 44
                    and struct.unpack_from(">I", data, offset + 12)[0] & 2,
                    "Distribution-signed simulator executable refused")
            directories += 1
        else:
            require(slot in {2, 5, 7}, "Simulator signer or unexpected signature slot refused")
    require(0 in slots and directories >= 1, "Ad-hoc CodeDirectory missing")


def simulator_executable(data):
    require(len(data) >= 32, "Simulator executable is truncated")
    magic, cpu, _subtype, filetype, count, length, _flags, _reserved = struct.unpack_from("<8I", data)
    require(magic == 0xFEEDFACF and cpu == 0x0100000C and filetype == 2
            and 0 < count <= 4096 and length <= 1024 * 1024 and 32 + length <= len(data),
            "Expected arm64 Mach-O application executable")
    offset, platforms, signatures = 32, [], []
    for _ in range(count):
        require(offset + 8 <= 32 + length, "Mach-O load command is truncated")
        kind, size = struct.unpack_from("<2I", data, offset)
        require(size >= 8 and offset + size <= 32 + length, "Malformed simulator executable refused")
        if kind == 0x32:
            require(size >= 24, "Simulator build-version command is truncated")
            platforms.append(struct.unpack_from("<I", data, offset + 8)[0])
        if kind == 0x1D:
            require(size == 16, "Simulator signature command differs")
            start, size_bytes = struct.unpack_from("<2I", data, offset + 8)
            require(32 + length <= start and 0 < size_bytes <= 16 * 1024 * 1024
                    and start + size_bytes <= len(data), "Simulator signature bounds differ")
            signatures.append(data[start:start + size_bytes])
        offset += size
    require(offset == 32 + length and platforms == [7], "Native executable does not target iOS Simulator")
    require(len(signatures) <= 1, "Duplicate simulator signature refused")
    if signatures:
        adhoc_signature(signatures[0])
    return "ad-hoc" if signatures else "none"


def _verify_adhoc_file(executable):
    try:
        command("codesign", "--verify", "--strict", str(executable))
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "") + (error.stdout or "")
        require(len(detail) <= 64 * 1024, "Unexpected code-signature verification output")
        detail = re.sub(r"[\r\n\t]+", " ", detail)
        detail = re.sub(r"[^\x20-\x7e]", "?", detail).strip()
        diagnostic = detail[:8192] + (" [truncated]" if len(detail) > 8192 else "")
        raise ValueError(f"Apple code signature verification failed (exit {error.returncode}): "
                         + (diagnostic or "no diagnostic output")) from None
    result = subprocess.run(["codesign", "--display", "--verbose=4", str(executable)],
                            check=True, capture_output=True, text=True, timeout=30)
    detail = result.stderr + result.stdout
    require(len(detail) <= 64 * 1024 and re.search(r"^Signature=adhoc$", detail, re.M)
            and re.search(r"^TeamIdentifier=not set$", detail, re.M)
            and not re.search(r"^Authority=", detail, re.M), "Simulator signing identity refused")


def verify_adhoc(executable):
    # CODE_SIGNING_ALLOWED=NO leaves the bundle without an Apple resource seal.
    # Verify the linker's existing executable signature as a standalone code item.
    data = regular_bytes(executable, FILE_LIMIT)
    before = {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    with tempfile.TemporaryDirectory(prefix="onesa-native-signature-") as directory:
        private = Path(directory)
        mode = private.lstat()
        resolved = private.resolve()
        require(stat.S_ISDIR(mode.st_mode) and stat.S_IMODE(mode.st_mode) == 0o700
                and mode.st_uid == os.getuid()
                and not resolved.is_relative_to(executable.parent.resolve())
                and all(path.suffix.lower() not in {".app", ".framework", ".appex", ".bundle", ".xpc"}
                        for path in (resolved, *resolved.parents)),
                "Signature verification requires an owned private directory outside bundles")
        copy = private / APP_NAME
        with os.fdopen(os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
            output.write(data)
        require(file_record(copy) == before and file_record(executable) == before,
                "Executable changed while preparing signature verification")
        try:
            _verify_adhoc_file(copy)
        finally:
            require(file_record(copy) == before and file_record(executable) == before,
                    "Executable changed during signature verification")


def ios_identity(app):
    require(not app.is_symlink() and app.is_dir(), "Native simulator application missing")
    info = plistlib.loads(regular_bytes(app / "Info.plist", 1024 * 1024))
    require(info.get("CFBundleIdentifier") == APP_ID and info.get("CFBundleExecutable") == APP_NAME
            and info.get("CFBundleSupportedPlatforms") == ["iPhoneSimulator"]
            and info.get("DTPlatformName") == "iphonesimulator" and info.get("UIDeviceFamily") == [1, 2],
            "Expected the Drone iPhone/iPad simulator application identity")
    require(not (app / "embedded.mobileprovision").exists() and not (app / "_CodeSignature").exists(),
            "Provisioned or separately signed simulator application refused")
    signing = simulator_executable(regular_bytes(app / APP_NAME, FILE_LIMIT))
    if signing == "ad-hoc":
        verify_adhoc(app / APP_NAME)
    files = {}
    total = 0
    for path in sorted(app.rglob("*")):
        require(not path.is_symlink(), "Simulator bundle symlink refused")
        if path.is_dir():
            continue
        require(path.is_file(), "Unexpected simulator bundle entry")
        relative = path.relative_to(app).as_posix()
        require(len(relative) <= 512 and all(32 <= ord(char) < 127 for char in relative)
                and not relative.endswith((".p12", ".p8", ".key", ".keystore", ".mobileprovision")),
                "Signing material or invalid simulator bundle path refused")
        record = file_record(path, allow_empty=True)
        total += record["size_bytes"]
        files[relative] = {**record, "executable": bool(path.stat().st_mode & 0o111)}
        require(len(files) <= 4096 and total <= BUNDLE_LIMIT, "Simulator bundle exceeds bounds")
    return {"application_id": APP_ID, "architecture": "arm64", "configuration": "debug",
            "code_signature": signing, "code_signature_scope": "main-executable",
            "code_signature_verification": "apple-strict-standalone-copy" if signing == "ad-hoc" else "not-signed",
            "bundle_resource_seal": "absent", "distribution_signed": False,
            "bundle_tree_sha256": hashlib.sha256(canonical(files)).hexdigest()}, files


def source_unchanged(root, source, platform):
    require(command("git", "-C", str(root), "rev-parse", "HEAD") == source["source_commit"],
            "Native source changed during compilation")
    changes = command("git", "-C", str(root), "diff", "--name-only", "HEAD", "--", ".").splitlines()
    prefix = source.get("source_path", ".")
    placeholder = (Path(prefix) / MOBILE_PATH / platform / "README.md").as_posix()
    require(changes == [placeholder], "Tracked source changed during native compilation")
    # Ask Git only for unexpected paths: generated Pods/build listings can exceed
    # the command output bound even when every path belongs to an allowed root.
    generated = [":(exclude,literal)" + (MOBILE_PATH / name).as_posix() + "/"
                 for name in (platform, ".validation")]
    untracked = command("git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z",
                        "--", ".", *generated)
    require(not untracked,
            "Untracked application source appeared during native compilation")


def qualify(platform, output, root=ROOT, *, bench=False):
    require(not bench or platform == "android", "Bench builds require Android")
    mobile = root / MOBILE_PATH
    prepared = json.loads(regular_bytes(output / "prepared.json", 64 * 1024))
    variant = prepared.pop("variant", "default")
    require(variant == ("bench" if bench else "default"), "Native build variant differs")
    require(set(prepared) == {"platform", "source", "inputs"} and prepared["platform"] == platform,
            "Native preparation identity differs")
    require(prepared["inputs"] == locked_inputs(mobile), "Locked inputs changed during native compilation")
    source_unchanged(root, prepared["source"], platform)
    require(command("node", "--version") == "v24.22.1", "Reviewed Node toolchain required")
    toolchain = {"node": "24.22.1"}
    if platform == "android":
        configuration = "release" if bench else "debug"
        apk = mobile / f"android/app/build/outputs/apk/{configuration}/app-{configuration}.apk"
        before = file_record(apk)
        sdk = Path(os.environ["ANDROID_HOME"])
        badging = command(str(sdk / "build-tools/37.0.0/aapt"), "dump", "badging", str(apk))
        identity = android_identity(apk, badging, bench=bench)
        if bench:
            verification = command(str(sdk / "build-tools/37.0.0/apksigner"), "verify",
                                   "--verbose", "--print-certs", str(apk))
            identity.update(bench_signer(verification))
        java = subprocess.run(["java", "-version"], check=True, capture_output=True, text=True, timeout=30)
        require(re.search(r'version "17\.', java.stderr + java.stdout), "Reviewed JDK 17 required")
        toolchain.update(jdk=17, gradle=GRADLE_VERSION, gradle_distribution_sha256=GRADLE_SHA256,
                         android=ANDROID_VERSIONS)
        artifact = output / ("OnesaDrone-arm64-bench.apk" if bench else "OnesaDrone-arm64-debug.apk")
        with artifact.open("xb") as destination, apk.open("rb") as source:
            shutil.copyfileobj(source, destination)
        require(file_record(artifact) == before, "Android output changed while retaining it")
    else:
        app = mobile / ".validation/ios-build/Build/Products/Debug-iphonesimulator/OnesaDrone.app"
        identity, files = ios_identity(app)
        toolchain.update(xcode=command("xcodebuild", "-version"), cocoapods=command("pod", "--version"),
                         simulator_sdk=command("xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"))
        lock = regular_bytes(mobile / "ios/Podfile.lock", 1024 * 1024)
        require(b"PODS:\n" in lock and b"SPEC CHECKSUMS:\n" in lock, "Resolved CocoaPods lock missing")
        with (output / "Podfile.lock").open("xb") as destination:
            destination.write(lock)
        toolchain["resolved_locks"] = {"ios/Podfile.lock": file_record(output / "Podfile.lock")}
        # Preserve any actual SwiftPM resolver locks too; never synthesize a lock.
        swift_locks = sorted((mobile / "ios").rglob("Package.resolved"))
        require(len(swift_locks) <= 8, "Unexpected SwiftPM resolver-lock count")
        for index, path in enumerate(swift_locks, 1):
            data = regular_bytes(path, 1024 * 1024)
            require(isinstance(json.loads(data), dict), "SwiftPM resolver lock differs")
            name = f"swiftpm-{index:02d}-Package.resolved"
            with (output / name).open("xb") as destination:
                destination.write(data)
            toolchain["resolved_locks"][path.relative_to(mobile).as_posix()] = {
                "retained_name": name, **file_record(output / name),
            }
        toolchain["resolver_lock_status"] = "first-resolution-observed"
        artifact = output / "OnesaDrone-arm64-simulator.tar.gz"
        with tarfile.open(artifact, "x:gz") as archive:
            for name, record in files.items():
                path = app / name
                require(file_record(path, allow_empty=True) == {key: record[key] for key in ("sha256", "size_bytes")},
                        "Simulator output changed before retention")
                item = tarfile.TarInfo(APP_NAME + ".app/" + name)
                item.size = record["size_bytes"]
                item.mode = 0o755 if record["executable"] else 0o644
                with path.open("rb") as stream:
                    archive.addfile(item, stream)
        require(ios_identity(app)[1] == files, "Simulator output changed while retaining it")
    proof = {
        "schema_version": 1, **prepared["source"], "component": "mobile", "platform": platform,
        "target": "android-arm64-debug" if platform == "android" else "ios-arm64-simulator",
        "mode": "simulation", "hardware_flight_enabled": False, "verification_only": True,
        "release_authorized": False, "qualification": "native-compilation-only", "identity": identity,
        "inputs": prepared["inputs"], "toolchain": toolchain,
        "output": {"name": artifact.name, **file_record(artifact)},
    }
    if bench:
        proof.update(target="android-arm64-bench", qualification="offline-bench-package",
                     device_launch_verified=False)
    with (output / "compile-proof.json").open("xb") as destination:
        destination.write(canonical(proof) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "qualify"))
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    parser.add_argument("--bench", action="store_true", help="Qualify a test-signed offline Android bench build")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        (prepare if args.action == "prepare" else qualify)(args.platform, args.output, bench=args.bench)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        raise SystemExit("Native compile qualification refused: " + str(error)) from None


if __name__ == "__main__":
    main()
