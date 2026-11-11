"""One-off offline QA using only the fresh hosted Android emulator and synthetic data."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

RUN = int(os.environ["BENCH_BUILD_RUN"])
SOURCE = os.environ["BENCH_SOURCE_SHA"]
if RUN <= 0 or not re.fullmatch(r"[0-9a-f]{40}", SOURCE):
    raise ValueError("Invalid fixed build run or source commit")
SERIAL = "emulator-5554"
PACKAGE = "eu.onesa.drone.bench"
COMPONENT = PACKAGE + "/eu.onesa.drone.MainActivity"
ASSET = "SyntheticBenchA77"
OBSERVATION = "Onesa Monitor shows actual aircraft position as unavailable, Observed"
TEMP = Path(os.environ["RUNNER_TEMP"])
APK = TEMP / "bench-artifact/OnesaDrone-arm64-bench.apk"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify():
    proof = json.loads((APK.parent / "compile-proof.json").read_text())
    with APK.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    require(proof["repository"] == "DruHustle/onesa-drone" and proof["source_commit"] == SOURCE,
            "Artifact source mismatch")
    require(proof["qualification"] == "offline-bench-package" and proof["target"] == "android-arm64-bench"
            and proof["mode"] == "simulation" and proof["hardware_flight_enabled"] is False
            and proof["release_authorized"] is False and proof["device_launch_verified"] is False,
            "Incorrect bench qualification")
    require(proof["identity"]["application_id"] == PACKAGE and proof["identity"]["architecture"] == "arm64-v8a",
            "Unexpected app identity")
    require(proof["identity"]["native_library_packaging"] == "compressed-for-install-time-extraction" and
            proof["identity"]["native_library_extraction"] in ("explicit", "platform-default"),
            "Expected bench package with native library extraction")
    require(proof["output"] == {"name": APK.name, "sha256": digest, "size_bytes": APK.stat().st_size},
            "APK size or digest differs from the build proof")
    print("Verified source", SOURCE, "and APK SHA-256", digest)
    return digest


def adb(*args, timeout=20, check=True):
    result = subprocess.run(["adb", "-s", SERIAL, *args], text=True,
                            capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError("adb failed: " + " ".join(args[:4]) + ": " + (result.stdout + result.stderr)[-400:])
    return result.stdout.strip()


def shell(*args, **kwargs):
    return adb("shell", *args, **kwargs)


def boot():
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        os.kill(int(os.environ["QA_EMULATOR_PID"]), 0)
        if shell("getprop", "sys.boot_completed", check=False) == "1":
            break
        time.sleep(2)
    else:
        raise RuntimeError("Emulator did not finish booting")
    require(shell("getprop", "ro.kernel.qemu") == "1" and shell("getprop", "ro.build.version.sdk") == "30",
            "Expected disposable Android 30 emulator")
    require(adb("emu", "avd", "name").splitlines()[0] == "OnesaBenchQA", "Incorrect AVD")
    abis = shell("getprop", "ro.product.cpu.abilist").split(",")
    require({"x86_64", "arm64-v8a"}.issubset(abis), "Image lacks arm64 translation: " + str(abis))
    shell("cmd", "connectivity", "airplane-mode", "enable")
    shell("svc", "wifi", "disable")
    shell("svc", "data", "disable")
    for name in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        shell("settings", "put", "global", name, "0")
    shell("wm", "size", "1200x2400")
    shell("wm", "density", "240")
    shell("wm", "dismiss-keyguard")
    verify_offline()


def verify_offline():
    for _ in range(20):
        airplane = shell("settings", "get", "global", "airplane_mode_on")
        wifi = shell("settings", "get", "global", "wifi_on")
        wifi_off = wifi == "0" or re.search(r"wi-?fi is disabled", shell("cmd", "wifi", "status"), re.I)
        # A connectivity readback also catches a default network on a different interface.
        connectivity = shell("dumpsys", "connectivity")
        if airplane == "1" and wifi_off and re.search(r"Active default network:\s*(?:none|null)\b",
                                                         connectivity, re.I):
            return
        time.sleep(1)
    raise RuntimeError("Emulator still has a default network or enabled Wi-Fi")


def launch():
    output = shell("am", "start", "-W", "-n", COMPONENT, timeout=75)
    require("Status: ok" in output, "Explicit launch failed: " + output[:240])
    print("Explicit bench activity launched")


def hierarchy():
    output = shell("uiautomator", "dump", "/sdcard/onesa-bench-ui.xml", check=False)
    if "dumped" not in output.lower():
        return []
    raw = adb("exec-out", "cat", "/sdcard/onesa-bench-ui.xml")
    root = ET.fromstring(raw)
    return [n.attrib for n in root.iter("node") if n.get("package") == PACKAGE]


def find(label, *, kind=None, scroll=False, pattern=False, duration=45):
    started = time.monotonic()
    last = []
    previous_view = None
    toward_bottom = True
    while time.monotonic() - started < duration:
        last = hierarchy()
        for node in last:
            if kind and node.get("class") != kind:
                continue
            for key in ("content-desc", "text"):
                value = node.get(key, "")
                if (re.fullmatch(label, value) if pattern else label == value):
                    bounds = [int(v) for v in re.findall(r"-?\d+", node["bounds"])]
                    if len(bounds) == 4 and bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                        return bounds, value
        if last and scroll:
            view = [(n.get("text"), n.get("content-desc"), n.get("bounds")) for n in last]
            if view == previous_view:
                toward_bottom = not toward_bottom
            previous_view = view
            start, end = ("1870", "850") if toward_bottom else ("850", "1870")
            shell("input", "swipe", "600", start, "600", end, "420")
        time.sleep(0.5)
    visible = [n.get("text") or n.get("content-desc") for n in last if n.get("text") or n.get("content-desc")]
    raise RuntimeError(f"Missing bench UI {label!r}. Last visible bench labels: {visible[-20:]}")


def tap(label, **kwargs):
    (left, top, right, bottom), _ = find(label, **kwargs)
    shell("input", "tap", str((left + right) // 2), str((top + bottom) // 2))


def exercise():
    digest = verify()
    boot()
    require("Success" in adb("install", "-t", str(APK), timeout=120), "APK installation failed")
    verify_offline()
    launch()
    tap("Monitor", duration=65)
    find("Not available")
    tap("Aircraft")
    tap("Aircraft asset label", kind="android.widget.EditText", scroll=True)
    shell("input", "text", ASSET)
    # No hardware keyboard is required. BACK closes only a visible soft keyboard.
    if re.search(r"mInputShown=true\b", shell("dumpsys", "input_method")):
        shell("input", "keyevent", "KEYCODE_BACK")
    tap("Start bench record", scroll=True)
    find(ASSET, scroll=True)
    tap(OBSERVATION, scroll=True)
    _, result = find(r"Observed\s*·\s*\d{4}-\d\d-\d\dT\S+Z", pattern=True, scroll=True)
    print("Saved a synthetic record and observed timestamp")
    shell("am", "force-stop", PACKAGE)
    require(not shell("pidof", PACKAGE, check=False), "Application did not terminate")
    launch()
    tap("Aircraft", duration=65)
    find(ASSET, scroll=True)
    find(result, scroll=True)
    verify_offline()
    report = {"source": SOURCE, "build_run": RUN, "apk_sha256": digest, "api": 30,
              "device": "Android emulator x86_64 with arm64 translation",
              "offline_install": True, "explicit_launch": True,
              "synthetic_worksheet_persisted_after_force_stop": True,
              "physical_device_tested": False}
    print(json.dumps(report))
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
        out.write("### Offline Android emulator check\n\n"
                  "The exact arm64 bench APK installed offline, launched by activity, and restored the "
                  "synthetic worksheet and its observation timestamp after a force-stop.\n\n"
                  f"Build run `{RUN}` · source `{SOURCE}` · APK SHA-256 `{digest}`\n")


def diagnostics():
    # This is an empty, account-free AVD. Collect failure evidence only from its
    # package UI or relevant runtime log tags. No APK or private app data is copied.
    target = TEMP / "bench-qa-failure"
    target.mkdir(exist_ok=True)
    logfile = TEMP / "qa-emulator.log"
    if logfile.is_file():
        (target / "emulator-tail.log").write_bytes(logfile.read_bytes()[-48_000:])
    sources = {
        "runtime-logcat.txt": ["logcat", "-d", "-t", "500", "ReactNativeJS:V", "ReactNative:V",
                               "SoLoader:V", "AndroidRuntime:E", "libc:F", "*:S"],
        "crash-buffer.txt": ["logcat", "-d", "-b", "crash", "-t", "200"],
        "package-state.txt": ["shell", "dumpsys", "package", PACKAGE],
    }
    for name, args in sources.items():
        try:
            raw = adb(*args, timeout=8)
            (target / name).write_text(raw[-96_000:])
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            print("Unable to read", name, str(exc)[:180])
    try:
        focus = shell("dumpsys", "window", "windows", timeout=8)
        current = re.search(r"mCurrentFocus=[^\n]*", focus)
        if current and PACKAGE in current.group():
            nodes = hierarchy()
            (target / "bench-visible-ui.json").write_text(json.dumps(nodes, indent=2))
    except (RuntimeError, subprocess.TimeoutExpired, ET.ParseError) as exc:
        print("Unable to capture bench UI", str(exc)[:180])


if __name__ == "__main__":
    {"verify": verify, "exercise": exercise, "diagnostics": diagnostics}[sys.argv[1]]()
