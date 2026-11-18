import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ios_simulator_selection", Path(__file__).resolve().parents[1] / "scripts/ios-simulator-ui/select_simulator.py"
)
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)

QUALIFIED = "com.apple.CoreSimulator.SimRuntime.iOS-26-4"
NEWER = "com.apple.CoreSimulator.SimRuntime.iOS-26-5"
PHONE = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro"
AIR = "com.apple.CoreSimulator.SimDeviceType.iPhone-Air"
RUNTIMES = {"runtimes": [
    {"identifier": QUALIFIED, "version": "26.4.1", "isAvailable": True},
    {"identifier": NEWER, "version": "26.5", "isAvailable": True},
]}
DEVICES = {"devices": {
    QUALIFIED: [{"deviceTypeIdentifier": PHONE, "isAvailable": True}],
    NEWER: [{"deviceTypeIdentifier": AIR, "isAvailable": True}],
}}


class SimulatorSelectionTests(unittest.TestCase):
    def test_qualified_actual_version_and_device_win_over_newer_defaults(self):
        self.assertEqual(
            selection.choose_simulator(DEVICES, RUNTIMES, version="26.4.1", device_type=PHONE),
            (QUALIFIED, PHONE, "26.4.1"),
        )

    def test_local_developer_can_explicitly_omit_both_pins(self):
        self.assertEqual(selection.choose_simulator(DEVICES, RUNTIMES), (NEWER, AIR, "26.5"))

    def test_missing_runtime_or_device_never_falls_back(self):
        for version, model in (("26.4", PHONE), ("27.0", PHONE), ("26.4.1", AIR)):
            with self.subTest(version=version, model=model), self.assertRaises(ValueError):
                selection.choose_simulator(DEVICES, RUNTIMES, version=version, device_type=model)

    def test_partial_or_invalid_configuration_is_rejected(self):
        for version, model in (("26.4.1", None), (None, PHONE), ("26.4.1\n", PHONE), ("26.4.1", "booted")):
            with self.subTest(version=version, model=model), self.assertRaises(ValueError):
                selection.choose_simulator(DEVICES, RUNTIMES, version=version, device_type=model)

    def test_unavailable_runtime_and_device_are_rejected(self):
        for flag in (False, "true", None):
            runtimes = copy.deepcopy(RUNTIMES)
            runtimes["runtimes"][0]["isAvailable"] = flag
            with self.subTest(runtime=flag), self.assertRaises(ValueError):
                selection.choose_simulator(DEVICES, runtimes, version="26.4.1", device_type=PHONE)
            devices = copy.deepcopy(DEVICES)
            devices["devices"][QUALIFIED][0]["isAvailable"] = flag
            with self.subTest(device=flag), self.assertRaises(ValueError):
                selection.choose_simulator(devices, RUNTIMES, version="26.4.1", device_type=PHONE)

    def test_empty_inventory_and_untrusted_identifiers_are_rejected(self):
        for devices, runtimes in (({"devices": {}}, RUNTIMES), (DEVICES, {"runtimes": []})):
            with self.assertRaises(ValueError):
                selection.choose_simulator(devices, runtimes)
        runtimes = {"runtimes": [{"identifier": QUALIFIED + "\nprivate", "version": "26.4.1", "isAvailable": True}]}
        with self.assertRaises(ValueError):
            selection.choose_simulator(DEVICES, runtimes)
        devices = {"devices": {QUALIFIED: [{"deviceTypeIdentifier": PHONE + "\nprivate", "isAvailable": True}]}}
        with self.assertRaises(ValueError):
            selection.choose_simulator(devices, RUNTIMES)
