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


def find(label, *, scroll=False, timeout=45, contains=False, widget=None, resource=None):
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
            identifier = node.get("resource-id", "").rsplit("/", 1)[-1]
            if (resource and identifier != resource) or (widget and node.get("class") != widget) or not any(
                (label in value if contains else label == value) for value in labels
            ):
                continue
            bounds = [int(value) for value in re.findall(r"-?\d+", node.get("bounds", ""))]
            if len(bounds) == 4 and bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                return (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2
        if scroll and nodes:
            viewport = [(n.get("resource-id"), n.get("bounds"), n.get("text"), n.get("content-desc")) for n in nodes]
            if previous == viewport:
                down = not down
            previous = viewport
            top, bottom = ("1850", "750") if down else ("750", "1850")
            shell("input", "swipe", "600", top, "600", bottom, "420")
        time.sleep(0.4)
    raise RuntimeError(f"Missing planner UI {label!r}")


def tap(label, **options):
    x, y = find(label, **options)
    shell("input", "tap", str(x), str(y))


def receipt(message):
    print("PASS: " + message, flush=True)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::notice title=Offline Android emulator::" + message, flush=True)
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write("- Passed — " + message + "\n")


def launch():
    result = shell("am", "start", "-W", "-n", APP_ID + "/.MainActivity", timeout=75)
    require("Status: ok" in result, "Android did not launch the release activity")


def restrict_app_network():
    # A booting emulator may advertise an Ethernet network even in airplane
    # mode. Its production app must be unable to reach that network, regardless
    # of Android's current choice of default network. Scope the packet policy
    # to this freshly installed UID on the named throwaway emulator.
    require(adb("emu", "avd", "name").splitlines()[0] == AVD, "Expected the disposable offline emulator")
    adb("root")
    adb("wait-for-device")
    require(shell("id", "-u") == "0", "Expected an SDK emulator that supports adb root")
    record = shell("cmd", "package", "list", "packages", "-U", APP_ID)
    match = re.fullmatch(r"package:" + re.escape(APP_ID) + r"\s+uid:(\d+)", record)
    require(match is not None and int(match[1]) >= 10000, "Could not determine installed release UID")
    uid = match[1]
    for tool in ("iptables", "ip6tables"):
        shell(tool, "-w", "3", "-I", "OUTPUT", "1", "!", "-o", "lo", "-m", "owner", "--uid-owner", uid, "-j", "REJECT")
    return uid


def verify_offline(uid):
    require(shell("settings", "get", "global", "airplane_mode_on") == "1", "Airplane mode is off")
    for tool in ("iptables", "ip6tables"):
        rules = shell(tool, "-w", "3", "-S", "OUTPUT").splitlines()
        first = next((rule for rule in rules if rule.startswith("-A OUTPUT ")), "")
        require("! -o lo" in first and ("--uid-owner " + uid + " ") in first and "-j REJECT" in first,
                "The app's non-loopback network traffic must be rejected by the first " + tool + " rule")


def screenshot(directory, name):
    if directory is None:
        return
    binary = Path(os.environ["ANDROID_HOME"]) / "platform-tools/adb"
    image = subprocess.check_output([str(binary), "-s", SERIAL, "exec-out", "screencap", "-p"])
    require(image.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid emulator screenshot")
    (directory / name).write_bytes(image)


def planning_and_share():
    tap("Aircraft")
    tap("A qualified remote pilot and visual line of sight are available", scroll=True, contains=True)
    find("1 / 4 reviewed · Physical dispatch remains locked.", scroll=True)
    find("Waypoint dispatch", scroll=True)
    find("Disabled", scroll=True)
    tap("Aircraft asset label", scroll=True, widget="android.widget.EditText")
    shell("input", "text", "Synthetic-A77-bench")
    shell("input", "keyevent", "KEYCODE_BACK")
    tap("Start bench record", scroll=True)
    find("Synthetic-A77-bench", scroll=True)
    tap("Share bench record", scroll=True, timeout=80)
    end = time.monotonic() + 15
    while not re.search(r"(?:topResumedActivity|mResumedActivity)[^\n]*(?:ChooserActivity|IntentResolver)",
                        shell("dumpsys", "activity", "activities"), re.I):
        require(time.monotonic() < end, "Expected the native Android sharesheet")
        time.sleep(0.4)
    shell("input", "keyevent", "KEYCODE_BACK")
    find("Share bench record", scroll=True)
    receipt("Human review count, hardware lockout, synthetic saved bench record and cancel native share")


def exercise(apk, screenshots=None):
    if screenshots:
        screenshots.mkdir(mode=0o700, parents=True, exist_ok=False)
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
                uid = restrict_app_network()
                verify_offline(uid)
                launch()
                find("Mission planner")
                receipt("Offline cold launch")
                tap("Load example", scroll=True)
                tap("Save encrypted draft", scroll=True)
                find("Example security perimeter", scroll=True)
                shell("am", "force-stop", APP_ID)
                require(not shell("pidof", APP_ID, check=False), "Android did not stop the app")
                launch()
                tap("Missions")
                find("Example security perimeter", scroll=True)
                tap("Open route", scroll=True)
                find("Mission planner", scroll=True)
                screenshot(screenshots, "01-offline-planner.png")
                receipt("Encrypted route reopened after force-stop")
                tap("Preview simulation", scroll=True)
                find("Not available", scroll=True, timeout=110)
                receipt("Simulator opened with actual A77 location unavailable")
                # Android's UIAutomator waits for accessibility events to settle
                # before dumping a view. The moving marker can keep it busy
                # until the replay has already reached its stable end state.
                find("100%", scroll=True, timeout=110, resource="replay-progress")
                receipt("Synthetic replay reached 100%")
                find("Play replay", scroll=True)
                screenshot(screenshots, "02-completed-synthetic-replay.png")
                tap("Reset", scroll=True)
                find("0%", scroll=True, resource="replay-progress")
                receipt("Completed synthetic replay reset to zero")
                tap("Video")
                find("No live feed", scroll=True)
                screenshot(screenshots, "03-hardware-video-unavailable.png")
                verify_offline(uid)
                receipt("No hardware camera feed; airplane mode and app IPv4/IPv6 isolation verified again")
                planning_and_share()
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
    parser.add_argument("--screenshots", type=Path, help="New directory for signed-out synthetic planner images")
    args = parser.parse_args()
    try:
        exercise(args.apk.resolve(strict=True), args.screenshots)
    except (RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            # Only the fixed expected UI label is safe to retain across runs.
            detail = str(exc) if isinstance(exc, RuntimeError) and str(exc).startswith("Missing planner UI ") else type(exc).__name__
            print("::error title=Offline Android emulator::" + detail, flush=True)
        raise
