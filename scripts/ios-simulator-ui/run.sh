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
  test) mode=planner ;;
  auth) mode=auth
    : "${FIXTURE_CA:?Run the paired acceptance harness}" "${ONESA_FIXTURE_PASSWORD:?}" "${ONESA_FIXTURE_FACTOR:?}" "${ONESA_FIXTURE_SECOND_FACTOR:?}"
    [[ "$EXPO_PUBLIC_DRONE_DEV_ORIGIN" == "https://127.0.0.1:54844" ]]
    ;;
  *) echo "Usage: $0 prepare|test|auth" >&2; exit 2 ;;
esac
cd "$mobile"
work=$(mktemp -d)
if [[ "$mode" == auth ]]; then
  # Xcode may record text entries/callbacks even with screenshots disabled. Only the summary leaves this directory.
  results="$work/account.xcresult"
else
  results=${IOS_UI_RESULTS:-"$mobile/.validation/simulator-ui.xcresult"}
fi
if [[ -e "$results" ]]; then echo "Choose a new IOS_UI_RESULTS path." >&2; exit 1; fi
mkdir -p "$(dirname "$results")"
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
# CoreSimulator can return zero for a terminal first-boot migration failure.
# Restart the same empty device once before installing the app or any test CA.
boot_simulator() {
  xcrun simctl bootstatus "$device" -b | tee "$work/boot.log" || return 1
  ! grep -Fq 'Data Migration Failed' "$work/boot.log"
}
if ! boot_simulator; then
  echo "First simulator boot did not finish. Retrying the same device once."
  xcrun simctl shutdown "$device" || true
  boot_simulator || { echo "Simulator boot failed twice." >&2; exit 1; }
fi
if [[ "$mode" == auth ]]; then
  xcrun simctl keychain "$device" add-root-cert "$FIXTURE_CA"
fi
if curl --noproxy '*' --silent --max-time 2 http://127.0.0.1:8081/status >/dev/null; then
  echo "Port 8081 already has a server. Stop it before running this checkout's Metro." >&2
  exit 1
fi
CI=1 EXPO_OFFLINE=1 EXPO_NO_TELEMETRY=1 node node_modules/expo/bin/cli start --localhost --port 8081 > "$work/metro.log" 2>&1 &
metro=$!
ready=false
for _ in {1..90}; do
  if ! kill -0 "$metro" 2>/dev/null; then cat "$work/metro.log" >&2; exit 1; fi
  if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8081/status 2>/dev/null | grep -Fq 'packager-status:running'; then ready=true; break; fi
  sleep 1
done
if [[ "$ready" != true ]]; then echo "Metro did not start." >&2; exit 1; fi
if [[ "$mode" == auth ]]; then
  selected=AccountTests/testPortalSignInAndSystemCallback
  export TEST_RUNNER_ONESA_FIXTURE_PASSWORD="$ONESA_FIXTURE_PASSWORD"
  export TEST_RUNNER_ONESA_FIXTURE_FACTOR="$ONESA_FIXTURE_FACTOR"
  export TEST_RUNNER_ONESA_FIXTURE_SECOND_FACTOR="$ONESA_FIXTURE_SECOND_FACTOR"
else
  selected=PlannerTests/testOfflineDraftSurvivesRelaunchAndHardwareStaysLocked
  if [[ -n "${IOS_UI_SCREENSHOTS:-}" ]]; then export TEST_RUNNER_ONESA_PLANNER_IMAGES=1; fi
fi
arguments=(test -workspace ios/OnesaDrone.xcworkspace -scheme OnesaDroneSimulatorUI
  -configuration Debug -destination "platform=iOS Simulator,id=$device" -parallel-testing-enabled NO
  -derivedDataPath .validation/ios-build -resultBundlePath "$results"
  "-only-testing:OnesaDroneSimulatorUI/$selected"
  ARCHS=arm64 ONLY_ACTIVE_ARCH=YES ENABLE_DEBUG_DYLIB=NO)
if [[ "$mode" == auth ]]; then
  if ! RCT_NO_LAUNCH_PACKAGER=1 xcodebuild "${arguments[@]}" > "$work/private-xcode.log" 2>&1; then
    # Only allowlisted test checkpoint names can be published. Never echo account forms, URLs or Xcode's artifact.
    python3 - "$work/private-xcode.log" <<'PYCODE'
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(errors="replace")
checkpoints = ["Standalone Portal browser", "Portal email field", "Portal MFA challenge",
               "Active Portal browser session", "Signed-out Drone planner", "Portal login in system browser",
               "Reused active Portal session without entering credentials", "OS callback returned the requested account",
               "Expected account authority", "Keychain session survives relaunch", "Revalidated account authority",
               "Confirmed central sign-out"]
for name in checkpoints:
    if name in text and ("failed - " + name in text or "failed: " + name in text):
        print("Failed installed iOS account checkpoint:", name)
PYCODE
    echo "Installed iOS sign-in did not pass." >&2
    exit 1
  fi
else
  RCT_NO_LAUNCH_PACKAGER=1 xcodebuild "${arguments[@]}"
fi
xcrun xcresulttool get test-results summary --path "$results" > "$work/summary.json"
receipt="$results.summary.json"
if [[ "$mode" == auth ]]; then receipt="$mobile/.validation/installed-account-summary.json"; fi
mkdir -p "$(dirname "$receipt")"
python3 - "$work/summary.json" "$receipt" "$runtime" "$model" "$(git rev-parse HEAD)" "$selected" <<'PY'
import json, sys
with open(sys.argv[1]) as result:
    summary = json.load(result)
if summary.get("passedTests") != 1 or summary.get("failedTests") != 0 or summary.get("skippedTests", 0):
    raise SystemExit("The required native UI test did not pass exactly once.")
receipt = {
    "source_commit": sys.argv[5], "runtime": sys.argv[3], "device_type": sys.argv[4],
    "test": sys.argv[6],
    "passed": 1, "failed": 0, "skipped": 0,
}
with open(sys.argv[2], "x") as output:
    json.dump(receipt, output, indent=2)
    output.write("\n")
print(json.dumps(receipt))
PY

if [[ "$mode" == planner && -n "${IOS_UI_SCREENSHOTS:-}" ]]; then
  container=$(xcrun simctl get_app_container "$device" eu.onesa.drone.simulator-ui.xctrunner data)
  mkdir -p "$IOS_UI_SCREENSHOTS"
  for filename in planner.png locked-video.png; do
    test -s "$container/Documents/$filename"
    cp "$container/Documents/$filename" "$IOS_UI_SCREENSHOTS/$filename"
  done
fi
