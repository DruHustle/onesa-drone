"""Select the configured installed runtime/device without downloading or falling back."""

import json
import os
import re
import sys
from pathlib import Path

RUNTIME = re.compile(r"com\.apple\.CoreSimulator\.SimRuntime\.iOS-\d+(?:-\d+){1,2}")
MODEL = re.compile(r"com\.apple\.CoreSimulator\.SimDeviceType\.iPhone-[A-Za-z0-9-]+")
VERSION = re.compile(r"\d+(?:\.\d+){1,2}")


def choose_simulator(devices, runtimes, *, version=None, device_type=None):
    if bool(version) != bool(device_type):
        raise ValueError("Configure both simulator runtime version and device type.")
    if version and (not VERSION.fullmatch(version) or not MODEL.fullmatch(device_type)):
        raise ValueError("Invalid simulator qualification pairing.")
    choices = set()
    for runtime in runtimes["runtimes"]:
        identifier = runtime.get("identifier", "")
        actual_version = runtime.get("version", "")
        if (runtime.get("isAvailable") is not True or not RUNTIME.fullmatch(identifier)
                or not VERSION.fullmatch(actual_version)):
            continue
        if version and version != actual_version:
            continue
        for device in devices["devices"].get(identifier, []):
            model = device.get("deviceTypeIdentifier", "")
            if device.get("isAvailable") is not True or not MODEL.fullmatch(model):
                continue
            if device_type and device_type != model:
                continue
            choices.add((tuple(map(int, actual_version.split("."))), identifier, model, actual_version))
    if not choices:
        raise ValueError("The requested installed iPhone/runtime pairing is unavailable; no fallback is permitted.")
    _, runtime, model, actual_version = max(choices)
    return runtime, model, actual_version


def main():
    try:
        devices = json.loads(Path(sys.argv[1]).read_text())
        runtimes = json.loads(Path(sys.argv[2]).read_text())
        runtime, model, version = choose_simulator(
            devices, runtimes,
            version=os.environ.get("ONESA_IOS_UI_RUNTIME_VERSION"),
            device_type=os.environ.get("ONESA_IOS_UI_DEVICE_TYPE"),
        )
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OSError):
        print("Installed simulator qualification pairing is unavailable or invalid; no fallback performed.", file=sys.stderr)
        return 1
    print("ONESA_SIMULATOR_SELECTION " + json.dumps({
        "runtime": runtime, "version": version, "deviceType": model,
    }), file=sys.stderr, flush=True)
    print(runtime, model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
