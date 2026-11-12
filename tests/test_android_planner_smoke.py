"""Offline acceptance requires stable disconnected radios, not a transition gap."""
import unittest
from unittest.mock import patch

from scripts import android_planner_smoke as smoke

OFFLINE = {"airplane": "1", "wifi": "0", "mobileData": "0", "defaultNetwork": "none"}


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class OfflineGateTests(unittest.TestCase):
    def run_gate(self, states, **options):
        clock = Clock()
        remaining = iter(states)
        state = dict(OFFLINE)

        def next_state():
            nonlocal state
            state = next(remaining, state)
            return state

        with patch.object(smoke, "offline_readback", side_effect=next_state), \
                patch.object(smoke.time, "monotonic", clock.monotonic), \
                patch.object(smoke.time, "sleep", clock.sleep):
            result = smoke.verify_offline(**options)
        return result, clock.now

    def test_temporary_disconnect_does_not_complete_before_wifi_restoration(self):
        states = [OFFLINE, OFFLINE, {**OFFLINE, "wifi": "2"},
                  {**OFFLINE, "wifi": "2", "defaultNetwork": "100"}]
        with self.assertRaisesRegex(ValueError, '"wifi": "2"'):
            self.run_gate(states, timeout=3, stable_for=2)

    def test_reconnection_restarts_the_entire_stable_observation_window(self):
        states = [OFFLINE, OFFLINE, {**OFFLINE, "defaultNetwork": "100"}, OFFLINE]
        result, elapsed = self.run_gate(states, timeout=4, stable_for=2)
        self.assertEqual(result, OFFLINE)
        self.assertEqual(elapsed, 3.5)

    def test_later_checkpoint_rejects_wifi_enabled_even_before_association(self):
        with self.assertRaisesRegex(ValueError, '"wifi": "2"'):
            self.run_gate([{**OFFLINE, "wifi": "2"}], timeout=0, stable_for=0)

    def test_explicit_airplane_disabled_wifi_is_accepted_with_no_network(self):
        expected = {**OFFLINE, "wifi": "3", "defaultNetwork": "null"}
        result, _ = self.run_gate([expected], timeout=0, stable_for=0)
        self.assertEqual(result, expected)

    def test_current_network_parser_rejects_history_and_ambiguous_fields(self):
        for dump in ("history: Active default network: none", "Active default network: 100\n"
                     "  Active default network: none", "SSID private-value"):
            with self.subTest(dump=dump), patch.object(smoke, "shell", side_effect=[dump, "1", "0", "0"]):
                self.assertEqual(smoke.offline_readback()["defaultNetwork"], "unknown")

    def test_readback_exposes_only_bounded_flags_and_current_network_identity(self):
        with patch.object(smoke, "shell", side_effect=[
            "Active default network: none\nprivate SSID and historical diagnostics", "1", "0", "0"
        ]):
            self.assertEqual(smoke.offline_readback(), OFFLINE)
        with patch.object(smoke, "shell", side_effect=["unrecognized private state", "secret", "9", "null"]):
            self.assertEqual(set(smoke.offline_readback().values()), {"unknown"})


if __name__ == "__main__":
    unittest.main()
