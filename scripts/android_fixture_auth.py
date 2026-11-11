"""Drive the real Expo debug client on the dedicated loopback identity emulator."""
import os
from pathlib import Path
import subprocess
import sys

from scripts.android_planner_smoke import adb, find, launch, shell, tap
from scripts.mobile_native_compile import APP_ID, require


def main():
    require(os.environ.get("EXPO_PUBLIC_DRONE_DEV_ORIGIN") == "https://127.0.0.1:54844"
            and adb("emu", "avd", "name").splitlines()[0] == "OnesaIdentityFixture"
            and shell("getprop", "ro.build.version.sdk") == "33", "Expected the disposable identity fixture")
    for role, label in (("member", "Fixture workspace · operator"), ("admin", "Portal administrator")):
        for state in ("signed-out", "active"):
            # Clear only the native app. Chrome's Portal cookies survive the
            # second launch. A warm return must complete without credentials.
            require(shell("pm", "clear", APP_ID) == "Success", "Could not reset disposable Drone client")
            launch()
            find("Mission planner", timeout=105)
            tap("Onesa account")
            tap("Sign in with Onesa")
            helper = Path(__file__).parent / "android-emulator-ui" / "portal.cjs"
            child = subprocess.run(["node", str(helper), role, state], capture_output=True, timeout=125)
            if child.returncode != 0:
                sys.exit(f"Android Chrome Portal form failed for {role} / {state} (stage {child.returncode})")
            find(label, timeout=85)
            find("Open my field planner")
            print(f"PASS Android 13 Chrome Custom Tab / {role} / {state} / native role")
        tap("Sign out of Onesa")
        find("Signed out of Onesa.", timeout=45)
        print(f"PASS Android / {role} / confirmed central sign-out")


if __name__ == "__main__":
    main()
