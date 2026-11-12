"""Drive the real Expo debug client on the dedicated loopback identity emulator."""
import os
import json
from pathlib import Path
import re
import subprocess
import sys

from scripts.android_planner_smoke import adb, find, launch, screenshot, shell, tap
from scripts.mobile_native_compile import APP_ID, require


def startup_classification(text, process_running):
    # Diagnostics may contain account values. Return fixed vocabulary only;
    # never publish a log line, UI label, URL, callback or exception message.
    signatures = {
        "system-ui-not-responding": ("System UI isn't responding", "System UI is not responding"),
        "application-not-responding": ("Onesa Drone isn't responding", "Onesa Drone is not responding"),
        "native-process-crash": ("FATAL EXCEPTION",),
        "metro-connection-unavailable": ("Unable to load script", "Could not connect to development server",
                                         "Unable to connect to Metro", "Failed to connect to /10.0.2.2:8081"),
        "javascript-runtime-error": ("JavascriptException", "TypeError:", "ReferenceError:",
                                     "Invariant Violation", "Unable to resolve module"),
        "planner-visible": ('text="Mission planner"', 'content-desc="Mission planner"'),
    }
    observed = [label for label, values in signatures.items() if any(value in text for value in values)]
    return {"stage": "initial-native-planner", "processRunning": bool(process_running),
            "observations": observed or ["no-recognized-signature"]}


def record_startup_failure(*, before_credentials):
    # A fresh AVD has no previous browser account at the first launch. Later
    # launches may expose account state, so only that first failure gets an image.
    diagnostics = ""
    running = False
    try:
        pid = shell("pidof", APP_ID, check=False)
        running = bool(re.fullmatch(r"[0-9]+", pid))
        if running:
            diagnostics = adb("logcat", "-d", "--pid=" + pid, "-v", "brief", "-t", "400")
        shell("uiautomator", "dump", "/data/local/tmp/onesa-startup.xml", check=False)
        diagnostics += adb("exec-out", "cat", "/data/local/tmp/onesa-startup.xml", check=False)
        result = startup_classification(diagnostics, running)
    except (OSError, subprocess.SubprocessError):
        result = {"stage": "initial-native-planner", "processRunning": running,
                  "observations": ["diagnostic-unavailable"]}
    print("Android startup failure: " + json.dumps(result), flush=True)
    if before_credentials:
        output = Path("frontend/drone/mobile/.validation/android-startup-failure")
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        try:
            screenshot(output, "before-account.png")
        except (OSError, ValueError, subprocess.SubprocessError):
            print("Pre-account screenshot unavailable.", flush=True)


def portal_observations(output):
    allowed = {"cdp-connected", "cdp-disconnected", "portal-sign-in", "portal-other-page",
               "browser-error-page", "native-callback", "other-page"}
    try:
        observed = json.loads(output[:4096])
        if isinstance(observed, list):
            return sorted({value for value in observed if isinstance(value, str) and value in allowed})
    except (ValueError, UnicodeError):
        pass
    return ["diagnostic-unavailable"]


def main():
    require(os.environ.get("EXPO_PUBLIC_DRONE_DEV_ORIGIN") == "https://127.0.0.1:54844"
            and adb("emu", "avd", "name").splitlines()[0] == "OnesaIdentityFixture"
            and shell("getprop", "ro.build.version.sdk") == "33", "Expected the disposable identity fixture")
    for role, label in (("member", "Fixture workspace · operator"), ("admin", "Portal administrator")):
        # Each role's first case is cold. The preceding role's confirmed central
        # logout is asserted below before this next-role browser reset.
        require(shell("pm", "clear", "com.android.chrome") == "Success",
                "Could not reset the disposable role's Chrome data")
        for state in ("signed-out", "active"):
            # Clear only the native app. Chrome's Portal cookies survive the
            # second launch. A warm return must complete without credentials.
            require(shell("pm", "clear", APP_ID) == "Success", "Could not reset disposable Drone client")
            launch()
            try:
                find("Mission planner", timeout=105)
            except (RuntimeError, subprocess.SubprocessError):
                record_startup_failure(before_credentials=role == "member" and state == "signed-out")
                raise
            tap("Onesa account")
            tap("Sign in with Onesa")
            helper = Path(__file__).parent / "android-emulator-ui" / "portal.cjs"
            child = subprocess.run(["node", str(helper), role, state], capture_output=True, timeout=125)
            if child.returncode != 0:
                print("Portal browser checkpoints: " + ", ".join(portal_observations(child.stdout)), flush=True)
                sys.exit(f"Android Chrome Portal form failed for {role} / {state} (stage {child.returncode})")
            find(label, timeout=85)
            find(f"Synthetic {role} · {role}@example.test")
            find("Open my field planner")
            print(f"PASS Android 13 Chrome Custom Tab / {role} / {state} / native role")
        tap("Sign out of Onesa")
        find("Signed out of Onesa.", timeout=45)
        print(f"PASS Android / {role} / confirmed central sign-out")


if __name__ == "__main__":
    main()
