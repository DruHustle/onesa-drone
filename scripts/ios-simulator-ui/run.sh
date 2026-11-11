#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
mobile="$repo/frontend/drone/mobile"
case "${1:-}" in
  prepare)
    # Resolve xcodeproj through the same Ruby/gems CocoaPods uses on this Mac.
    cd "$mobile"
    hook='require File.expand_path("../../../../scripts/ios-simulator-ui/target", __dir__)'
    if ! grep -Fxq "$hook" ios/Podfile; then printf '\n%s\n' "$hook" >> ios/Podfile; fi
    pod install --project-directory=ios
    exit 0
    ;;
  test) ;;
  *) echo "Usage: $0 prepare|test" >&2; exit 2 ;;
esac
cd "$mobile"
results=${IOS_UI_RESULTS:-"$mobile/.validation/simulator-ui.xcresult"}
if [[ -e "$results" ]]; then echo "Choose a new IOS_UI_RESULTS path." >&2; exit 1; fi
mkdir -p "$(dirname "$results")"
work=$(mktemp -d)
device=''
metro=''
cleanup() {
  if [[ -n "$metro" ]]; then kill "$metro" 2>/dev/null || true; wait "$metro" 2>/dev/null || true; fi
  if [[ -n "$device" ]]; then xcrun simctl shutdown "$device" 2>/dev/null || true; xcrun simctl delete "$device" || true; fi
  rm -rf "$work"
}
trap cleanup EXIT
# Choose an installed iPhone/runtime pairing, then create an entirely fresh
# simulator so the first-launch Keychain and subsequent persistence are observable.
xcrun simctl list devices available -j > "$work/devices.json"
read -r runtime model < <(python3 - "$work/devices.json" <<'PY'
import json, re, sys
with open(sys.argv[1]) as data:
    devices = json.load(data)["devices"]
choices = []
for runtime, installed in devices.items():
    version = re.fullmatch(r"com\.apple\.CoreSimulator\.SimRuntime\.iOS-(\d+(?:-\d+)*)", runtime)
    if version:
        for item in installed:
            model = item.get("deviceTypeIdentifier", "")
            if item.get("isAvailable") and ".iPhone-" in model:
                choices.append((tuple(map(int, version[1].split("-"))), runtime, model))
if not choices:
    raise SystemExit("Install an iOS Simulator runtime and an iPhone simulator in Xcode.")
_, runtime, model = max(choices)
print(runtime, model)
PY
)
device=$(xcrun simctl create "Onesa Drone UI $$" "$model" "$runtime")
xcrun simctl boot "$device"
xcrun simctl bootstatus "$device" -b
if curl --noproxy '*' --silent --max-time 2 http://127.0.0.1:8081/status >/dev/null; then
  echo "Port 8081 already has a server. Stop it before running this checkout's Metro." >&2
  exit 1
fi
CI=1 EXPO_NO_TELEMETRY=1 node node_modules/expo/bin/cli start --offline --localhost --port 8081 > "$work/metro.log" 2>&1 &
metro=$!
ready=false
for _ in {1..90}; do
  if ! kill -0 "$metro" 2>/dev/null; then cat "$work/metro.log" >&2; exit 1; fi
  if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8081/status 2>/dev/null | grep -Fq 'packager-status:running'; then ready=true; break; fi
  sleep 1
done
if [[ "$ready" != true ]]; then echo "Metro did not start." >&2; exit 1; fi
RCT_NO_LAUNCH_PACKAGER=1 xcodebuild test -workspace ios/OnesaDrone.xcworkspace -scheme OnesaDroneSimulatorUI \
  -configuration Debug -destination "platform=iOS Simulator,id=$device" -parallel-testing-enabled NO \
  -derivedDataPath .validation/ios-build -resultBundlePath "$results" \
  -only-testing:OnesaDroneSimulatorUI/PlannerTests/testOfflineDraftSurvivesRelaunchAndHardwareStaysLocked \
  ARCHS=arm64 ONLY_ACTIVE_ARCH=YES ENABLE_DEBUG_DYLIB=NO
xcrun xcresulttool get test-results summary --path "$results" > "$work/summary.json"
python3 - "$work/summary.json" "$results.summary.json" "$runtime" "$model" "$(git rev-parse HEAD)" <<'PY'
import json, sys
with open(sys.argv[1]) as result:
    summary = json.load(result)
if summary.get("passedTests") != 1 or summary.get("failedTests") != 0 or summary.get("skippedTests", 0):
    raise SystemExit("The required native UI test did not pass exactly once.")
receipt = {
    "source_commit": sys.argv[5], "runtime": sys.argv[3], "device_type": sys.argv[4],
    "test": "PlannerTests/testOfflineDraftSurvivesRelaunchAndHardwareStaysLocked",
    "passed": 1, "failed": 0, "skipped": 0,
}
with open(sys.argv[2], "x") as output:
    json.dump(receipt, output, indent=2)
    output.write("\n")
print(json.dumps(receipt))
PY
