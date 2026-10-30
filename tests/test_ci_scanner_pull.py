import subprocess
from unittest.mock import patch

from scripts.pull_ci_scanner import SCANNER, main


def test_success_uses_the_exact_pinned_scanner_without_retry():
    with (
        patch("scripts.pull_ci_scanner.subprocess.run") as run,
        patch("scripts.pull_ci_scanner.time.sleep") as sleep,
    ):
        run.return_value.returncode = 0
        assert main() == 0
        run.assert_called_once_with(["docker", "pull", SCANNER], timeout=120, check=False)
        sleep.assert_not_called()


def test_transient_download_failure_retries_the_same_digest():
    with (
        patch("scripts.pull_ci_scanner.subprocess.run") as run,
        patch("scripts.pull_ci_scanner.time.sleep") as sleep,
    ):
        run.side_effect = [
            subprocess.CompletedProcess([], 125),
            subprocess.CompletedProcess([], 0),
        ]
        assert main() == 0
        assert run.call_count == 2
        assert all(call.args[0] == ["docker", "pull", SCANNER] for call in run.call_args_list)
        sleep.assert_called_once_with(5)


def test_permanent_failure_remains_a_failed_gate_after_three_attempts():
    with (
        patch("scripts.pull_ci_scanner.subprocess.run") as run,
        patch("scripts.pull_ci_scanner.time.sleep") as sleep,
    ):
        run.return_value.returncode = 125
        assert main() == 1
        assert run.call_count == 3
        assert sleep.call_count == 2


def test_repeated_timeouts_are_bounded_and_fail_closed():
    with (
        patch("scripts.pull_ci_scanner.subprocess.run") as run,
        patch("scripts.pull_ci_scanner.time.sleep") as sleep,
    ):
        run.side_effect = subprocess.TimeoutExpired(["docker", "pull", SCANNER], 120)
        assert main() == 1
        assert run.call_count == 3
        assert all(call.kwargs["timeout"] == 120 for call in run.call_args_list)
        assert sleep.call_count == 2
