"""Check release-only identity and signer validation using synthetic local inputs."""

import base64
import hashlib
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
        der = b"demo signer fixture"
        certificate = hashlib.sha256(der).hexdigest()
        pem = "-----BEGIN CERTIFICATE-----\n" + base64.b64encode(der).decode() + "\n-----END CERTIFICATE-----"
        report = "Verified using v2 scheme (APK Signature Scheme v2): true\nSigner #1 certificate DN: CN=Fixture\n" + pem
        verify_signer(report, certificate)
        for value in [report.replace(pem, ""), report.replace(": true", ": false"),
                      report.replace("CN=Fixture", "CN=Android Debug"), report + "\n" + pem,
                      report.replace(base64.b64encode(der).decode(), "bm90IHRoZSBwaW4=")]:
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
