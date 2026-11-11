#!/usr/bin/env bash
# Disposable debug app and rooted SDK emulator. No attached device is selected.
set -euo pipefail
test "${1:-}" = auth
test "${EXPO_PUBLIC_DRONE_DEV_ORIGIN:-}" = 'https://127.0.0.1:54844'
test -f "${FIXTURE_CA:?}"
repo=$(cd "$(dirname "$0")/../.." && pwd)
cd "$repo"
mobile="$repo/frontend/drone/mobile"
work=$(mktemp -d)
chmod 700 "$work"
emulator=''; metro=''
cleanup() {
  if [[ -n "$metro" ]]; then kill "$metro" 2>/dev/null || true; wait "$metro" 2>/dev/null || true; fi
  if [[ -n "$emulator" ]]; then kill "$emulator" 2>/dev/null || true; wait "$emulator" 2>/dev/null || true; fi
  rm -rf -- "$work"
}
trap cleanup EXIT
export ANDROID_AVD_HOME="$work/avd" ANDROID_EMULATOR_HOME="$work/emulator-home"
mkdir -p "$ANDROID_AVD_HOME" "$ANDROID_EMULATOR_HOME"
adb_bin="$ANDROID_HOME/platform-tools/adb"
device() { "$adb_bin" -s emulator-5582 "$@"; }
booted() {
  local deadline=$((SECONDS+300))
  until [[ "$(device shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]]; do
    kill -0 "$emulator"; [[ $SECONDS -lt $deadline ]] || return 1; sleep 2
  done
}
test -z "$("$adb_bin" devices | awk '$1=="emulator-5582"{ print $1 }')"
image='system-images;android-33;google_apis;x86_64'
echo no | "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" create avd --name OnesaIdentityFixture --package "$image" --device pixel
"$ANDROID_HOME/emulator/emulator" -avd OnesaIdentityFixture -port 5582 -writable-system -no-window -no-audio -no-snapshot \
  -no-boot-anim -no-metrics -gpu swiftshader_indirect -accel on -memory 3072 -cores 2 > "$work/emulator.log" 2>&1 &
emulator=$!
booted
test "$(device emu avd name | head -1 | tr -d '\r')" = OnesaIdentityFixture
test "$(device shell getprop ro.build.version.sdk | tr -d '\r')" = 33
test "$(device shell getprop ro.product.cpu.abi | tr -d '\r')" = x86_64
device root; device wait-for-device
device disable-verity
device reboot; device wait-for-device; booted
device root; device wait-for-device; device remount
# This AVD is the last Android generation whose system CAs live in this path.
# Install one generated CA here and read it back after restart. Never use the
# host machine's CA store or weaken the app/network security configuration.
ca_name=$(openssl x509 -in "$FIXTURE_CA" -subject_hash_old -noout)
[[ $ca_name =~ ^[a-f0-9]{8}$ ]]
device push "$FIXTURE_CA" "/system/etc/security/cacerts/$ca_name.0"
device shell chmod 644 "/system/etc/security/cacerts/$ca_name.0"
device shell chcon u:object_r:system_file:s0 "/system/etc/security/cacerts/$ca_name.0"
device reboot; device wait-for-device; booted
device exec-out cat "/system/etc/security/cacerts/$ca_name.0" | cmp - "$FIXTURE_CA"
device shell pm path com.android.chrome | grep -q '^package:'
device shell am set-debug-app --persistent com.android.chrome
printf '%s\n' '_ --disable-fre --no-first-run --no-default-browser-check --disable-features=TranslateUI' > "$work/chrome-command-line"
device push "$work/chrome-command-line" /data/local/tmp/chrome-command-line
device shell cmd role add-role-holder android.app.role.BROWSER com.android.chrome
device shell wm size 1200x2400
device shell wm density 240
device shell wm dismiss-keyguard
for port in 54844 54843 8081; do device reverse "tcp:$port" "tcp:$port"; done
export CHROME_DEVTOOLS_PORT
CHROME_DEVTOOLS_PORT=$(device forward tcp:0 localabstract:chrome_devtools_remote)
(cd "$mobile" && CI=1 EXPO_NO_TELEMETRY=1 EXPO_OFFLINE=1 exec node node_modules/expo/bin/cli start --localhost --port 8081) > "$work/metro.log" 2>&1 &
metro=$!
for attempt in {1..90}; do
  if ! kill -0 "$metro" 2>/dev/null; then
    sed -n '/^CommandError:/p' "$work/metro.log" >&2
    echo "Metro exited before the local fixture became ready." >&2
    exit 1
  fi
  if curl --noproxy '*' --max-time 2 --silent --fail http://127.0.0.1:8081/status | grep -q 'packager-status:running'; then break; fi
  if [[ $attempt == 90 ]]; then echo "Metro did not become ready on loopback within 90 attempts." >&2; exit 1; fi
  sleep 1
done
apk="$mobile/android/app/build/outputs/apk/debug/app-debug.apk"
test -s "$apk"
device install "$apk"
python -u -m scripts.android_fixture_auth
