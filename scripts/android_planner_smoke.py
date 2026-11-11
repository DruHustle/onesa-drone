"""Exercise the store release on a new offline Android 15 emulator using the SDK and ADB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from scripts.mobile_native_compile import APP_ID, require

SERIAL = "emulator-5582"
AVD = "OnesaPlannerSmoke"
IMAGE = "system-images;android-35;google_apis;x86_64"


def adb(*args, check=True, timeout=25):
    binary = Path(os.environ["ANDROID_HOME"]) / "platform-tools/adb"
    proc = subprocess.run([str(binary), "-s", SERIAL, *args], capture_output=True, text=True,
                          check=check, timeout=timeout)
    return proc.stdout.strip()


def shell(*args, **kwargs):
    return adb("shell", *args, **kwargs)


def find(label, *, scroll=False, timeout=45):
    deadline = time.monotonic() + timeout
    previous = None
    down = True
    while time.monotonic() < deadline:
        dump = shell("uiautomator", "dump", "/sdcard/onesa-test.xml", check=False)
        if "dumped" not in dump.lower():
            time.sleep(0.5)
            continue
        xml = adb("exec-out", "cat", "/sdcard/onesa-test.xml")
        nodes = [node for node in ET.fromstring(xml).iter("node") if node.get("package") == APP_ID]
        for node in nodes:
            labels = (node.get("text", ""), node.get("content-desc", ""))
            if label not in labels:
                continue
            bounds = [int(value) for value in re.findall(r"-?\d+", node.get("bounds", ""))]
            if len(bounds) == 4 and bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                return (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2
        if scroll and nodes:
            if previous == xml:
                down = not down
            previous = xml
            top, bottom = ("1850", "750") if down else ("750", "1850")
            shell("input", "swipe", "600", top, "600", bottom, "420")
        time.sleep(0.4)
    raise RuntimeError(f"Missing planner UI {label!r}")


def tap(label, *, scroll=False):
    x, y = find(label, scroll=scroll)
    shell("input", "tap", str(x), str(y))


def launch():
    result = shell("am", "start", "-W", "-n", APP_ID + "/.MainActivity", timeout=75)
    require("Status: ok" in result, "Android did not launch the release activity")


def verify_offline():
    require(shell("settings", "get", "global", "airplane_mode_on") == "1"
            and re.search(r"Active default network:\s*(?:none|null)\b", shell("dumpsys", "connectivity"), re.I),
            "Emulator must be offline for this test")


def exercise(apk):
    sdk = Path(os.environ["ANDROID_HOME"])
    emulator = sdk / "emulator/emulator"
    devices = subprocess.check_output([str(sdk / "platform-tools/adb"), "devices"], text=True)
    require(not any(line.split()[:1] == [SERIAL] for line in devices.splitlines()),
            "Emulator port 5582 is already in use")
    with tempfile.TemporaryDirectory(prefix="onesa-planner-avd-") as tmp:
        home = Path(tmp)
        folder = home / "avd"
        folder.mkdir()
        env = {**os.environ, "ANDROID_USER_HOME": tmp, "ANDROID_EMULATOR_HOME": tmp, "ANDROID_AVD_HOME": str(folder)}
        avd_path = folder / (AVD + ".avd")
        subprocess.run([str(sdk / "cmdline-tools/latest/bin/avdmanager"), "create", "avd", "--name", AVD,
                        "--path", str(avd_path), "--package", IMAGE, "--device", "pixel"], input="no\n",
                       text=True, check=True, env=env, timeout=90)
        if not (folder / (AVD + ".ini")).exists():
            (folder / (AVD + ".ini")).write_text(f"avd.ini.encoding=UTF-8\npath={avd_path}\ntarget=android-35\n")
        with (home / "emulator.log").open("w") as log:
            process = subprocess.Popen([str(emulator), "-avd", AVD, "-port", "5582", "-accel", "on",
                                        "-gpu", "swiftshader_indirect", "-no-window", "-no-audio", "-no-snapshot",
                                        "-no-boot-anim", "-camera-front", "none", "-camera-back", "none",
                                        "-cores", "2", "-memory", "3072"], stdout=log, stderr=log, env=env)
            try:
                deadline = time.monotonic() + 300
                while shell("getprop", "sys.boot_completed", check=False) != "1":
                    require(process.poll() is None and time.monotonic() < deadline, "Android emulator failed to boot")
                    time.sleep(2)
                require(process.poll() is None and adb("emu", "avd", "name").splitlines()[0] == AVD
                        and shell("getprop", "ro.build.version.sdk") == "35"
                        and shell("getprop", "ro.product.cpu.abi") == "x86_64", "Wrong Android test environment")
                for setting in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
                    shell("settings", "put", "global", setting, "0")
                shell("wm", "size", "1200x2400")
                shell("wm", "density", "240")
                shell("wm", "dismiss-keyguard")
                shell("cmd", "connectivity", "airplane-mode", "enable")
                shell("svc", "wifi", "disable")
                shell("svc", "data", "disable")
                require("Success" in adb("install", str(apk), timeout=90), "Could not install universal APK")
                verify_offline()
                launch()
                find("Mission planner")
                print("PASS: offline cold launch")
                tap("Load example", scroll=True)
                tap("Save encrypted draft", scroll=True)
                find("Example security perimeter", scroll=True)
                shell("am", "force-stop", APP_ID)
                require(not shell("pidof", APP_ID, check=False), "Android did not stop the app")
                launch()
                tap("Missions")
                find("Example security perimeter", scroll=True)
                tap("Open route", scroll=True)
                print("PASS: saved encrypted route reopened after force-stop")
                tap("Preview simulation", scroll=True)
                find("Not available", scroll=True, timeout=110)
                # Android's UIAutomator waits for accessibility events to settle
                # before dumping a view. The moving marker can keep it busy
                # until the replay has already reached its stable end state.
                find("100%", scroll=True, timeout=110)
                find("Play replay", scroll=True)
                tap("Reset", scroll=True)
                find("0%", scroll=True)
                print("PASS: simulated route reached 100%, reset to zero and showed no actual GPS")
                tap("Video")
                find("No live feed", scroll=True)
                verify_offline()
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    with apk.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    print(json.dumps({"androidApi": 35, "device": "x86_64 emulator", "apkSha256": digest,
                      "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                      "offlineDraftAfterRestart": "passed", "simulatedReplay": "passed",
                      "actualPositionAndVideoUnavailable": "passed"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    exercise(parser.parse_args().apk.resolve(strict=True))
