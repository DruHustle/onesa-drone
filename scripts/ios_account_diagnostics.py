"""Reduce private XCTest output to fixed account stages and bounded source locations."""

import json
import re
import sys
from pathlib import Path


def summarize(text):
    checkpoints = []
    for role, state, phase in re.findall(
        r"ONESA_ACCOUNT_CHECKPOINT (member|admin):(cold|warm):"
        r"(start|account-screen-ready|sign-in-tapped|browser-wait-failed|browser-ready|credentials-filled|mfa-visible|submitted|"
        r"identity-returned|keychain-restored|central-logout)\b", text
    ):
        value = f"{role}:{state}:{phase}"
        if value not in checkpoints:
            checkpoints.append(value)
    patterns = {
        "test-started": r"Test Case .*testPortalSignInAndSystemCallback.* started",
        "test-failed": r"Test Case .*testPortalSignInAndSystemCallback.* failed",
        "test-run-failed": r"\*\* TEST FAILED \*\*",
        "test-build-failed": r"\*\* TEST BUILD FAILED \*\*",
        "compiler-error": r"(?m)^.*\.(?:swift|m|mm|h):\d+:\d+: error:",
        "simulator-boot-failed": r"(?:Failed to boot|Unable to boot|Data Migration Failed)",
        "runner-launch-failed": r"(?:Failed to launch|Failed to establish communication|Early unexpected exit)",
        "assertion-failed": r"XCTAssert\w* failed|XCTUnwrap failed",
    }
    categories = [name for name, pattern in patterns.items() if re.search(pattern, text)]
    lines = sorted({int(line) for line in re.findall(
        r"AccountTests\.swift:(\d{1,4})(?::\d+)?: error:", text
    )})[:20]
    states = []
    for role, state, flag in re.findall(
        r"ONESA_ACCOUNT_STATE (member|admin):(cold|warm):"
        r"(app-foreground|safari-foreground|auth-sheet-foreground|consent-continue-visible|"
        r"sign-in-enabled|sign-in-disabled|contacting-visible|service-unavailable-visible|"
        r"session-rejected-visible|cancelled-visible|invalid-start-visible|network-failure-visible|"
        r"app-webview-visible|browser-webview-visible|email-field-visible)(?=\r?$)", text, re.MULTILINE
    ):
        value = f"{role}:{state}:{flag}"
        if value not in states:
            states.append(value)
    result = {"checkpoints": checkpoints, "categories": categories or ["unclassified-failure"],
              "account_test_source_lines": lines}
    if states:
        result["observed_states"] = states
    return result


if __name__ == "__main__":
    print(json.dumps(summarize(Path(sys.argv[1]).read_text(errors="replace"))))
