import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location(
    "ios_simulator_boot", Path(__file__).resolve().parents[1] / "scripts/ios-simulator-ui/boot.py"
)
simulator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(simulator)

DEVICE = "11111111-2222-4333-8444-555555555555"
FINISHED = "[2026-11-16 11:20:26 +0000] Status=4294967295, isTerminal=YES, Elapsed=02:19.\n\tFinished\n"
MIGRATION_FAILURE = "[2026-11-16 11:24:13 +0000] Status=3, isTerminal=YES, Elapsed=02:03.\n\tData Migration Failed\n"


class SimulatorBootTests(unittest.TestCase):
    def test_zero_exit_with_actual_migration_failure_is_rejected(self):
        self.assertEqual(simulator.classify_boot(0, MIGRATION_FAILURE), "terminal-failure")

    def test_unknown_terminal_failure_and_prior_failure_are_rejected(self):
        for output in (
            "Status=7, isTerminal=YES, Elapsed=00:01.\nFinished\n",
            MIGRATION_FAILURE + FINISHED,
        ):
            with self.subTest(output=output):
                self.assertEqual(simulator.classify_boot(0, output), "terminal-failure")

    def test_only_completed_success_passes(self):
        for output in (FINISHED, FINISHED.replace("4294967295", "-1")):
            self.assertEqual(simulator.classify_boot(0, output), "ready")
        self.assertEqual(simulator.classify_boot(1, FINISHED), "command-failed")

    def test_empty_unknown_and_incomplete_output_fail_closed(self):
        for output in (
            "", "Device already booted", "Finished\n",
            "Status=4, isTerminal=NO, Elapsed=00:01.\nWaiting on System App\n",
            FINISHED.replace("Finished", ""),
            FINISHED + "Status=4, isTerminal=NO, Elapsed=00:02.\n",
        ):
            with self.subTest(output=output):
                self.assertEqual(simulator.classify_boot(0, output), "incomplete")

    def test_fresh_boot_is_bounded_and_captures_only_simctl_output(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, FINISHED))
        self.assertEqual(simulator.boot(DEVICE, run), "ready")
        run.assert_called_once_with(
            ["xcrun", "simctl", "bootstatus", DEVICE, "-b"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            timeout=300, check=False,
        )

    def test_timeout_and_missing_command_fail_without_retrying_the_device(self):
        for error, expected in (
            (subprocess.TimeoutExpired("xcrun", 300), "timeout"),
            (FileNotFoundError("xcrun"), "command-unavailable"),
        ):
            run = Mock(side_effect=error)
            self.assertEqual(simulator.boot(DEVICE, run), expected)
            run.assert_called_once()

    def test_named_or_implicit_existing_device_cannot_be_targeted(self):
        run = Mock()
        for device in ("booted", "iPhone", "--help", DEVICE + "\n"):
            self.assertEqual(simulator.boot(device, run), "invalid-device")
        run.assert_not_called()
