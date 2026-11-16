"""Require a completed fresh simulator boot before installing any app or fixture."""

import json
import re
import subprocess
import sys
import time

BOOT_TIMEOUT = 300


def classify_boot(returncode, output):
    # simctl can exit zero with terminal Status=3 (Data Migration Failed).
    # Require its actual terminal success, not just the process exit status.
    states = re.findall(r"Status=(-?\d+), isTerminal=(YES|NO),", output)
    terminal = [int(status) for status, final in states if final == "YES"]
    if "Data Migration Failed" in output or any(status not in (-1, 4294967295) for status in terminal):
        return "terminal-failure"
    if returncode:
        return "command-failed"
    if not states or states[-1][1] != "YES" or not terminal or not re.search(r"(?m)^\s*Finished\s*$", output):
        return "incomplete"
    return "ready"


def boot(device, run=subprocess.run):
    if not re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", device):
        return "invalid-device"
    try:
        # -b both starts and monitors this newly created device. Do not invoke
        # a separate boot first: a completed boot can otherwise evade the log.
        result = run(
            ["xcrun", "simctl", "bootstatus", device, "-b"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            timeout=BOOT_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    except OSError:
        return "command-unavailable"
    return classify_boot(result.returncode, result.stdout)


def main():
    start = time.monotonic()
    category = boot(sys.argv[1]) if len(sys.argv) == 2 else "invalid-device"
    print("ONESA_SIMULATOR_BOOT " + json.dumps({
        "status": "PASS" if category == "ready" else "FAIL", "category": category,
        "timeoutSeconds": BOOT_TIMEOUT,
        "elapsedMilliseconds": min(600000, max(0, int((time.monotonic() - start) * 1000))),
    }), flush=True)
    return 0 if category == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
