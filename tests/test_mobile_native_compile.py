"""Synthetic native-output adversaries; no SDK, device, signer or network is invoked."""

import copy
import hashlib
import json
from pathlib import Path
import plistlib
import stat
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from scripts import mobile_native_compile as native


def executable(*, platform=7, cpu=0x0100000C, signing=None):
    commands = [struct.pack("<6I", 0x32, 24, platform, 0, 0, 0)]
    signature = b""
    if signing is not None:
        directory = struct.pack(">11I", 0xFADE0C02, 44, 0x20400, 2 if signing == "ad-hoc" else 0,
                                0, 0, 0, 0, 0, 0, 0)
        signature = struct.pack(">5I", 0xFADE0CC0, 64, 1, 0, 20) + directory
        commands.append(struct.pack("<4I", 0x1D, 16, 72, len(signature)))
    length = sum(map(len, commands))
    header = struct.pack("<8I", 0xFEEDFACF, cpu, 0, 2, len(commands), length, 0, 0)
    return header + b"".join(commands) + signature


class NativeOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def android(self, *, machine=183, extra=None):
        apk = self.root / "app-debug.apk"
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", header, 18, machine)
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"synthetic compiled manifest")
            archive.writestr("classes.dex", b"dex\n035\x00synthetic")
            archive.writestr("lib/arm64-v8a/libreactnative.so", header)
            if extra:
                archive.writestr(extra, b"synthetic")
        return apk

    def ios(self, *, signing=None):
        app = self.root / "OnesaDrone.app"
        app.mkdir()
        info = {"CFBundleIdentifier": native.APP_ID, "CFBundleExecutable": native.APP_NAME,
                "CFBundleSupportedPlatforms": ["iPhoneSimulator"], "DTPlatformName": "iphonesimulator",
                "UIDeviceFamily": [1, 2]}
        (app / "Info.plist").write_bytes(plistlib.dumps(info))
        (app / native.APP_NAME).write_bytes(executable(signing=signing))
        (app / native.APP_NAME).chmod(0o755)
        return app

    def test_android_requires_debug_identity_and_actual_arm64_native_payload(self):
        badging = "package: name='eu.onesa.drone' versionCode='1'\napplication-debuggable\n"
        self.assertEqual(native.android_identity(self.android(), badging)["architecture"], "arm64-v8a")
        for invalid in (badging.replace("eu.onesa.drone", "eu.onesa.other"),
                        badging.replace("application-debuggable", "")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                native.android_identity(self.android(), invalid)
        for kwargs in ({"machine": 62}, {"extra": "../outside"}, {"extra": "lib/x86_64/other.so"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                native.android_identity(self.android(**kwargs), badging)

    def test_apk_symlink_member_is_refused(self):
        badging = "package: name='eu.onesa.drone' versionCode='1'\napplication-debuggable\n"
        apk = self.android()
        with zipfile.ZipFile(apk, "a") as archive:
            item = zipfile.ZipInfo("secret-link")
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(item, "/outside")
        with self.assertRaises(ValueError):
            native.android_identity(apk, badging)

    def test_simulator_requires_arm64_ios_simulator_mach_o(self):
        self.assertEqual(native.simulator_executable(executable()), "none")
        for data in (executable(platform=2), executable(cpu=0x01000007), b"not a native binary",
                     executable()[:-1]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                native.simulator_executable(data)

    def test_linker_adhoc_is_distinguished_from_distribution_signing(self):
        self.assertEqual(native.simulator_executable(executable(signing="ad-hoc")), "ad-hoc")
        with self.assertRaises(ValueError):
            native.simulator_executable(executable(signing="distribution"))
        signature = bytearray(executable(signing="ad-hoc"))
        struct.pack_into(">I", signature, 84, 0x10000)  # A CMS signer slot is never accepted.
        with self.assertRaises(ValueError):
            native.simulator_executable(bytes(signature))

    def test_adhoc_payload_also_requires_apple_signature_verification(self):
        app = self.ios(signing="ad-hoc")
        with patch.object(native, "verify_adhoc") as verify:
            identity, _files = native.ios_identity(app)
        verify.assert_called_once_with(app / native.APP_NAME)
        self.assertEqual(identity["code_signature"], "ad-hoc")
        self.assertEqual(identity["code_signature_scope"], "main-executable")
        self.assertEqual(identity["code_signature_verification"], "apple-strict-standalone-copy")
        self.assertEqual(identity["bundle_resource_seal"], "absent")
        self.assertIs(identity["distribution_signed"], False)
        with patch.object(native, "verify_adhoc", side_effect=ValueError("bad code hashes")):
            with self.assertRaises(ValueError):
                native.ios_identity(app)

    def test_apple_signature_rejection_preserves_bounded_diagnostics_and_refusal(self):
        path = self.root / "OnesaDrone.app/OnesaDrone"
        for stderr, output, expected in (
            ("synthetic validation rejection\n", "", "synthetic validation rejection"),
            ("", "synthetic stdout\x00detail", "synthetic stdout?detail"),
            ("\x1b[31mrejection\r\n\twith details\n", "", "?[31mrejection with details"),
            (None, None, "no diagnostic output"),
            ("x" * 10000, "", "[truncated]"),
            ("x" * (64 * 1024 + 1), "", "Unexpected code-signature verification output"),
        ):
            error = subprocess.CalledProcessError(1, ["codesign", "--verify", "--strict", str(path)],
                                                 output=output, stderr=stderr)
            with self.subTest(expected=expected), patch.object(native, "command", side_effect=error) as command, \
                    patch.object(native.subprocess, "run") as display, self.assertRaises(ValueError) as caught:
                native._verify_adhoc_file(path)
            command.assert_called_once_with("codesign", "--verify", "--strict", str(path))
            display.assert_not_called()
            self.assertIn(expected, str(caught.exception))
            self.assertLessEqual(len(str(caught.exception)), 8300)

    def test_strict_signature_check_uses_owned_exact_copy_and_cleans_it(self):
        original = self.ios(signing="ad-hoc") / native.APP_NAME
        before = original.read_bytes()
        copies = []

        def verify(*args):
            self.assertEqual(args[:3], ("codesign", "--verify", "--strict"))
            copy = Path(args[3])
            copies.append(copy)
            self.assertEqual(copy.read_bytes(), before)
            self.assertFalse(copy.is_relative_to(original.parent))
            self.assertEqual(stat.S_IMODE(copy.parent.stat().st_mode), 0o700)
            self.assertEqual(copy.parent.stat().st_uid, native.os.getuid())
            self.assertEqual(stat.S_IMODE(copy.stat().st_mode), 0o600)
            return ""

        with patch.object(native, "command", side_effect=verify), \
                patch.object(native.subprocess, "run", return_value=SimpleNamespace(
                    stdout="", stderr="Signature=adhoc\nTeamIdentifier=not set\n")) as display:
            native.verify_adhoc(original)
        self.assertEqual(len(copies), 1)
        display.assert_called_once_with(["codesign", "--display", "--verbose=4", str(copies[0])],
                                        check=True, capture_output=True, text=True, timeout=30)
        self.assertFalse(copies[0].parent.exists())
        self.assertEqual(original.read_bytes(), before)

    def test_signature_copy_refuses_mutation_tool_failure_or_signing_identity(self):
        original = self.ios(signing="ad-hoc") / native.APP_NAME
        before = original.read_bytes()
        for failure in ("original", "copy", "verify", "display", "identity", "original-after-display", "copy-after-display"):
            original.write_bytes(before)
            copies = []

            def verify(*args):
                copy = Path(args[3])
                copies.append(copy)
                if failure in {"original", "copy"}:
                    (original if failure == "original" else copy).write_bytes(b"changed")
                if failure == "verify":
                    raise subprocess.CalledProcessError(1, args, stderr="synthetic code-hash refusal")
                return ""

            def display(*args, **kwargs):
                if failure == "display":
                    raise subprocess.CalledProcessError(1, args[0], stderr="synthetic display refusal")
                if failure.endswith("-after-display"):
                    (original if failure.startswith("original") else copies[0]).write_bytes(b"changed")
                return SimpleNamespace(stdout="", stderr="Signature=adhoc\nTeamIdentifier="
                                       + ("unexpected" if failure == "identity" else "not set") + "\n")

            with self.subTest(failure=failure), patch.object(native, "command", side_effect=verify), \
                    patch.object(native.subprocess, "run", side_effect=display), \
                    self.assertRaises((ValueError, subprocess.CalledProcessError)):
                native.verify_adhoc(original)
            self.assertEqual(len(copies), 1)
            self.assertFalse(copies[0].parent.exists())

    def test_signature_copy_creation_failure_cleans_the_owned_directory(self):
        original = self.ios(signing="ad-hoc") / native.APP_NAME
        before = original.read_bytes()
        copies = []
        original_open = native.os.open

        def fail_copy(path, *args, **kwargs):
            if Path(path).name == native.APP_NAME:
                copies.append(Path(path))
                raise OSError("synthetic copy creation failure")
            return original_open(path, *args, **kwargs)

        with patch.object(native.os, "open", side_effect=fail_copy), \
                patch.object(native, "command") as command, self.assertRaises(OSError):
            native.verify_adhoc(original)
        command.assert_not_called()
        self.assertEqual(len(copies), 1)
        self.assertFalse(copies[0].parent.exists())
        self.assertEqual(original.read_bytes(), before)

    def test_signature_copy_rejects_unbounded_or_linked_input_and_bundle_temp_directory(self):
        original = self.ios(signing="ad-hoc") / native.APP_NAME
        link = self.root / "linked-executable"
        link.symlink_to(original)
        other_bundle = self.root / "Other.APP"
        other_bundle.mkdir()
        with patch.object(native, "command") as command:
            with self.assertRaises(ValueError):
                native.verify_adhoc(link)
            with patch.object(native, "FILE_LIMIT", 1), self.assertRaises(ValueError):
                native.verify_adhoc(original)
            for parent in (original.parent, other_bundle):
                with self.subTest(parent=parent), tempfile.TemporaryDirectory(dir=parent) as inside:
                    with patch.object(native.tempfile, "TemporaryDirectory") as temporary:
                        temporary.return_value.__enter__.return_value = inside
                        with self.assertRaisesRegex(ValueError, "outside bundles"):
                            native.verify_adhoc(original)
            command.assert_not_called()

    def test_ios_qualifies_source_bytes_and_detects_mutation(self):
        app = self.ios()
        (app / "empty-resource").write_bytes(b"")
        identity, files = native.ios_identity(app)
        self.assertEqual(identity["code_signature"], "none")
        self.assertEqual(files["empty-resource"]["size_bytes"], 0)
        self.assertTrue(files[native.APP_NAME]["executable"])
        (app / "resource").write_text("changed")
        self.assertNotEqual(native.ios_identity(app)[0]["bundle_tree_sha256"], identity["bundle_tree_sha256"])

    def test_ios_rejects_device_identity_and_signing_material(self):
        app = self.ios()
        info = plistlib.loads((app / "Info.plist").read_bytes())
        original = copy.deepcopy(info)
        for key, value in (("CFBundleIdentifier", "eu.onesa.other"), ("CFBundleSupportedPlatforms", ["iPhoneOS"]),
                           ("DTPlatformName", "iphoneos"), ("UIDeviceFamily", [1])):
            info = {**original, key: value}
            (app / "Info.plist").write_bytes(plistlib.dumps(info))
            with self.subTest(key=key), self.assertRaises(ValueError):
                native.ios_identity(app)
        (app / "Info.plist").write_bytes(plistlib.dumps(original))
        (app / "embedded.mobileprovision").write_text("synthetic")
        with self.assertRaises(ValueError):
            native.ios_identity(app)
        (app / "embedded.mobileprovision").unlink()
        (app / "signing.p12").write_text("synthetic")
        with self.assertRaises(ValueError):
            native.ios_identity(app)

    def test_ios_rejects_external_links_and_bundle_bounds(self):
        app = self.ios()
        (app / "outside").symlink_to(self.root / "outside")
        with self.assertRaises(ValueError):
            native.ios_identity(app)
        (app / "outside").unlink()
        with patch.object(native, "BUNDLE_LIMIT", 1), self.assertRaises(ValueError):
            native.ios_identity(app)

    def test_preserving_native_customizations_does_not_run_prebuild(self):
        mobile = self.root / native.MOBILE_PATH
        (mobile / "ios").mkdir(parents=True)
        custom = mobile / "ios/Local.swift"
        custom.write_text("existing local source")
        with patch.object(native, "locked_inputs", return_value={}), \
                patch.object(native, "source_binding", return_value={"source_commit": "a" * 40}), \
                patch.object(native.subprocess, "run") as run, self.assertRaises(ValueError):
            native.prepare("ios", self.root / "output", self.root)
        run.assert_not_called()
        self.assertEqual(custom.read_text(), "existing local source")

    def test_source_advance_or_other_tracked_change_invalidates_proof(self):
        source = {"source_commit": "a" * 40, "source_path": "onesa-drone"}
        placeholder = "onesa-drone/frontend/drone/mobile/ios/README.md"
        with patch.object(native, "command", side_effect=["a" * 40, placeholder, ""]):
            native.source_unchanged(self.root, source, "ios")
        for responses in (["b" * 40], ["a" * 40, placeholder + "\nonesa-drone/frontend/drone/mobile/App.js"],
                          ["a" * 40, placeholder, "frontend/drone/mobile/injected.js"]):
            with self.subTest(responses=responses), patch.object(native, "command", side_effect=responses), \
                    self.assertRaises(ValueError):
                native.source_unchanged(self.root, source, "ios")

    def test_large_generated_trees_preserve_exact_untracked_source_boundary(self):
        for prefix in ("", "onesa-drone"):
            for platform in ("ios", "android"):
                with self.subTest(prefix=prefix, platform=platform):
                    checkout = self.root / (prefix or "standalone") / platform
                    root = checkout / prefix if prefix else checkout
                    mobile = root / native.MOBILE_PATH
                    placeholder = mobile / platform / "README.md"
                    placeholder.parent.mkdir(parents=True)
                    placeholder.write_text("tracked native placeholder")
                    tracked = mobile / "App.js"
                    tracked.write_text("tracked application source")

                    def git(*args):
                        return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()

                    git("init", "--quiet")
                    git("add", ".")
                    git("-c", "user.name=Synthetic source fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "--quiet", "-m", "Synthetic native source")
                    source = {"source_commit": git("rev-parse", "HEAD"), "source_path": prefix or "."}
                    placeholder.unlink()
                    generated = placeholder.parent / "GeneratedHeaders"
                    generated.mkdir()
                    for index in range(512):
                        (generated / (f"Generated{index:04d}" + "a" * 100 + ".h")).write_text("synthetic")
                    build = mobile / ".validation/build"
                    build.mkdir(parents=True)
                    (build / "output").write_text("synthetic")
                    with self.assertRaisesRegex(ValueError, "Unexpected toolchain output"):
                        native.command("git", "-C", str(root), "ls-files", "--others", "--exclude-standard",
                                       "--", ".")
                    native.source_unchanged(root, source, platform)
                    other = "android" if platform == "ios" else "ios"
                    for name in ("injected.js", platform + "-spoof/Injected.h", ".validation-spoof/Injected.txt",
                                 other + "/Injected.txt", " space.js", "\n"):
                        path = mobile / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("unexpected application source")
                        with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Untracked application"):
                            native.source_unchanged(root, source, platform)
                        path.unlink()
                    tracked.write_text("changed tracked source")
                    with self.assertRaisesRegex(ValueError, "Tracked source changed"):
                        native.source_unchanged(root, source, platform)

    def prepared(self, platform):
        output = self.root / "evidence"
        output.mkdir()
        source = {"repository": "DruHustle/onesa-ug", "source_path": "onesa-drone",
                  "source_commit": "a" * 40, "source_tree": "b" * 40, "product_source_tree": "c" * 40}
        (output / "prepared.json").write_text(json.dumps({"platform": platform, "source": source, "inputs": {}}))
        return output

    def test_android_proof_binds_exact_retained_bytes_without_release_authority(self):
        output = self.prepared("android")
        apk = self.root / native.MOBILE_PATH / "android/app/build/outputs/apk/debug/app-debug.apk"
        apk.parent.mkdir(parents=True)
        apk.write_bytes(self.android().read_bytes())
        badging = "package: name='eu.onesa.drone' versionCode='1'\napplication-debuggable\n"
        with patch.object(native, "locked_inputs", return_value={}), \
                patch.object(native, "source_unchanged"), \
                patch.object(native, "command", side_effect=["v24.22.1", badging]), \
                patch.object(native.os, "environ", {"ANDROID_HOME": "/synthetic-sdk"}), \
                patch.object(native.subprocess, "run", return_value=SimpleNamespace(
                    stderr='openjdk version "17.0.1"', stdout="")):
            native.qualify("android", output, self.root)
        proof = json.loads((output / "compile-proof.json").read_text())
        retained = output / proof["output"]["name"]
        self.assertEqual(retained.read_bytes(), apk.read_bytes())
        self.assertEqual(proof["output"]["sha256"], hashlib.sha256(apk.read_bytes()).hexdigest())
        self.assertEqual(proof["source_commit"], "a" * 40)
        self.assertIs(proof["verification_only"], True)
        self.assertIs(proof["release_authorized"], False)
        self.assertIs(proof["hardware_flight_enabled"], False)
        self.assertEqual(proof["qualification"], "native-compilation-only")

    def test_ios_proof_retains_only_simulator_app_and_actual_resolver_locks(self):
        output = self.prepared("ios")
        app = self.ios()
        destination = self.root / native.MOBILE_PATH / ".validation/ios-build/Build/Products/Debug-iphonesimulator"
        destination.mkdir(parents=True)
        app.rename(destination / app.name)
        ios = self.root / native.MOBILE_PATH / "ios"
        ios.mkdir()
        (ios / "Podfile.lock").write_text("PODS:\n  - Synthetic (1.0)\nSPEC CHECKSUMS:\n  Synthetic: fixture\n")
        swift = ios / "OnesaDrone.xcworkspace/xcshareddata/swiftpm/Package.resolved"
        swift.parent.mkdir(parents=True)
        swift.write_text('{"pins": [], "version": 3}')
        with patch.object(native, "locked_inputs", return_value={}), \
                patch.object(native, "source_unchanged"), \
                patch.object(native, "command", side_effect=["v24.22.1", "Xcode fixture", "1.16.2", "26.0"]):
            native.qualify("ios", output, self.root)
        proof = json.loads((output / "compile-proof.json").read_text())
        self.assertEqual(proof["identity"]["code_signature"], "none")
        self.assertEqual(proof["toolchain"]["resolver_lock_status"], "first-resolution-observed")
        self.assertEqual((output / "Podfile.lock").read_bytes(), (ios / "Podfile.lock").read_bytes())
        self.assertEqual((output / "swiftpm-01-Package.resolved").read_bytes(), swift.read_bytes())
        artifact = output / proof["output"]["name"]
        self.assertEqual(proof["output"]["sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
        with native.tarfile.open(artifact) as archive:
            self.assertEqual(set(archive.getnames()), {"OnesaDrone.app/Info.plist", "OnesaDrone.app/OnesaDrone"})


class NativeInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mobile = Path(self.temp.name)
        dependencies = {"expo": native.EXPO_VERSION, "react-native": "0.88.1"}
        self.package = {"dependencies": dependencies}
        self.lock = {"lockfileVersion": 3, "packages": {"": {"dependencies": dependencies}}}
        for name, version in dependencies.items():
            path = self.mobile / "node_modules" / name
            path.mkdir(parents=True)
            (path / "package.json").write_text(json.dumps({"version": version}))
            self.lock["packages"]["node_modules/" + name] = {"version": version}
        self.config = {"expo": {"name": "Onesa Drone", "ios": {"bundleIdentifier": native.APP_ID,
                       "supportsTablet": True}, "android": {"package": native.APP_ID},
                       "userInterfaceStyle": "automatic", "updates": {"enabled": False},
                       "extra": {"simulationOnly": True, "hardwareFlightEnabled": False}}}
        (self.mobile / "node_modules/expo/template.tgz").write_bytes(b"synthetic template")
        versions = self.mobile / "node_modules/react-native/gradle/libs.versions.toml"
        versions.parent.mkdir()
        versions.write_text("[versions]\n" + "\n".join(f'{key} = "{value}"'
                                                     for key, value in native.ANDROID_VERSIONS.items()))
        self.write()
        self.pin = patch.object(native, "TEMPLATE_SHA256", hashlib.sha256(b"synthetic template").hexdigest())
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def write(self):
        for name, value in (("package.json", self.package), ("package-lock.json", self.lock),
                            ("app.json", self.config)):
            (self.mobile / name).write_text(json.dumps(value))

    def test_installed_locked_sdk_and_local_template_are_bound(self):
        value = native.locked_inputs(self.mobile)
        self.assertEqual(set(value["files_sha256"]), {"package.json", "package-lock.json", "app.json"})
        (self.mobile / "node_modules/expo/template.tgz").write_bytes(b"changed template")
        with self.assertRaises(ValueError):
            native.locked_inputs(self.mobile)

    def test_configuration_or_dependency_drift_is_refused(self):
        for mutate in (
            lambda: self.config["expo"]["extra"].update(hardwareFlightEnabled=True),
            lambda: self.package["dependencies"].update(expo="~58.0.23"),
        ):
            with self.subTest(mutate=mutate):
                package, config = copy.deepcopy(self.package), copy.deepcopy(self.config)
                mutate()
                self.write()
                with self.assertRaises(ValueError):
                    native.locked_inputs(self.mobile)
                self.package, self.config = package, config
                self.write()
        (self.mobile / "node_modules/expo/package.json").write_text('{"version":"58.0.24"}')
        with self.assertRaises(ValueError):
            native.locked_inputs(self.mobile)


if __name__ == "__main__":
    unittest.main()
