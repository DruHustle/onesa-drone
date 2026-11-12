"""Reduce private XCTest output to fixed account stages and bounded source locations."""

import json
import math
import re
import sys
from pathlib import Path


def summarize(text):
    checkpoints = []
    for role, state, phase in re.findall(
        r"ONESA_ACCOUNT_CHECKPOINT (member|admin):(cold|warm):"
        r"(start|account-screen-ready|sign-in-tapped|consent-tapped|browser-wait-failed|browser-ready|credentials-filled|mfa-visible|submitted|"
        r"unexpected-credential-route|interaction-not-observed|retry-visible-form-touch|"
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
        "keyboard-focus-missing": r"(?i)neither element nor any descendant has keyboard focus|does not have keyboard focus",
        "input-event-unavailable": r"(?i)failed to synthesize (?:a |the )?(?:key|event)|failed to send key event",
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
        r"session-rejected-visible|cancelled-visible|invalid-start-visible|network-failure-visible|timeout-failure-visible|tls-failure-visible|"
        r"app-webview-visible|browser-webview-visible|email-field-visible)(?=\r?$)", text, re.MULTILINE
    ):
        value = f"{role}:{state}:{flag}"
        if value not in states:
            states.append(value)
    result = {"checkpoints": checkpoints, "categories": categories or ["unclassified-failure"],
              "account_test_source_lines": lines}
    if states:
        result["observed_states"] = states
    frames = []
    for role, state, stage, payload in re.findall(
        r"ONESA_ACCOUNT_BUTTON (member|admin):(cold|warm):(before|failure):(\{[^\r\n]{1,512}\})(?=\r?$)", text, re.MULTILINE
    ):
        try:
            value = json.loads(payload)
            coordinates = {"x", "y", "width", "height"}
            booleans = {"exists", "enabled", "hittable", "centerInWindow"}
            if (not isinstance(value, dict) or set(value) != coordinates | booleans
                    or any(type(value[k]) not in (int, float) or not math.isfinite(value[k])
                           or not -10000 <= value[k] <= 10000 for k in coordinates)
                    or value["width"] < 0 or value["height"] < 0
                    or any(type(value[k]) is not bool for k in booleans)):
                continue
            frame = {"scenario": f"{role}:{state}", "stage": stage, **value}
            if frame not in frames and len(frames) < 8:
                frames.append(frame)
        except (ValueError, TypeError):
            pass
    if frames:
        result["button_geometry"] = frames
    return result


if __name__ == "__main__":
    print(json.dumps(summarize(Path(sys.argv[1]).read_text(errors="replace"))))
