"""The offline release gate waits for radio teardown and fails closed."""
import unittest
from unittest.mock import patch

from scripts import android_planner_smoke as smoke


class OfflineGateTests(unittest.TestCase):
    def test_waits_until_airplane_mode_and_no_default_network_are_observed(self):
        replies = iter([
            "0", "Active default network: 100\n",
            "1", "Active default network: 100\n",
            "1", "Active default network: none\n",
        ])
        with patch.object(smoke, "shell", side_effect=lambda *args: next(replies)), \
                patch.object(smoke.time, "monotonic", side_effect=[0, 0, 1]), \
                patch.object(smoke.time, "sleep") as sleep:
            smoke.verify_offline(timeout=2)
        self.assertEqual(sleep.call_count, 2)

    def test_accepts_explicit_absent_default_network(self):
        for absent in ("none", "null"):
            with self.subTest(absent=absent), \
                    patch.object(smoke, "shell", side_effect=["1", f"  Active default network: {absent}\n"]):
                smoke.verify_offline(timeout=0)

    def test_rejects_connected_unknown_or_airplane_disabled_after_deadline(self):
        for airplane, network in (
            ("0", "Active default network: none"),
            ("1", "Active default network: 100"),
            ("1", "No default network field"),
            ("1", "Active default network: none-but-connected"),
        ):
            with self.subTest(airplane=airplane, network=network), \
                    patch.object(smoke, "shell", side_effect=[airplane, network]), \
                    patch.object(smoke.time, "monotonic", side_effect=[0, 1]), \
                    patch.object(smoke.time, "sleep") as sleep:
                with self.assertRaisesRegex(ValueError, "Emulator must be offline"):
                    smoke.verify_offline(timeout=1)
                sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
