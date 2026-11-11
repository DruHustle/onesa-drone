"""Check release-only identity and signer validation using synthetic local inputs."""

import tempfile
import unittest
from pathlib import Path
import zipfile

from scripts.mobile_android_distribution import payload_hash, release_version, verify_signer


class AndroidDistributionTests(unittest.TestCase):
    def test_release_application(self):
        metadata = "package: name='eu.onesa.drone' versionCode='1' versionName='0.1.0' platformBuildVersionCode='37'"
        self.assertEqual(release_version(metadata), {"versionName": "0.1.0", "versionCode": 1})
        for value in [metadata + "\napplication-debuggable", metadata.replace("eu.onesa.drone", "other.app")]:
            with self.assertRaises(ValueError):
                release_version(value)

    def test_single_pinned_distribution_signer(self):
        certificate = "a" * 64
        report = ("Verified using v2 scheme (APK Signature Scheme v2): true\n"
                  "Signer #1 certificate DN: CN=Fixture\nSigner #1 certificate SHA-256 digest: " + certificate)
        verify_signer(report, certificate)
        for value in [report.replace(certificate, "b" * 64), report.replace(": true", ": false"),
                      report.replace("CN=Fixture", "CN=Android Debug"),
                      report + "\nSigner #2 certificate SHA-256 digest: " + certificate]:
            with self.assertRaises(ValueError):
                verify_signer(value, certificate)

    def test_payload_digest_compares_every_member_and_requires_bundled_application(self):
        names = ["AndroidManifest.xml", "classes.dex", "assets/index.android.bundle", "lib/arm64-v8a/libreactnative.so"]
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "sample.apk"
            def create(members, data):
                with zipfile.ZipFile(file, "w") as archive:
                    for name in members:
                        archive.writestr(name, name.encode() + data)
                return payload_hash(file)
            first = create(names, b"")
            self.assertEqual(first, create(reversed(names), b""))
            self.assertNotEqual(first, create(names, b"modified"))
            with self.assertRaises(ValueError):
                create(names[:-1], b"")
