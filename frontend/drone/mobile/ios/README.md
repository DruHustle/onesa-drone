# iOS native target

This Expo/React Native application is developed at the `../` root. Run `npm ci --ignore-scripts --no-audit --no-fund`, then `npx expo prebuild --platform ios` to generate the Xcode workspace inside this directory. Use `npm run ios` on macOS with a supported Xcode installation.

The A77 is **not** paired to this app. There is no CHUBORY SDK or supported remote GPS/video interface in this project. Apple Keychain backs encrypted route drafts. Native build, signing, TestFlight, simulator acceptance and device testing are release gates, not claims of completion.

## Ground bench trial on an iPhone

On a Mac with Xcode, prepare the iOS project in a fresh checkout as described above. Use an Apple development team authorized for the app identifier and a connected development-enabled iPhone. From the mobile directory, run `npx expo run:ios --configuration Release --device` to embed the JavaScript and select the phone. The CI artifact targets the arm64 simulator. An iPhone bench trial requires its own device-signed build.

Open **Aircraft → A77 ground bench record**, save an observation, close the app, and reopen it offline to verify Keychain persistence on the handset.


### Run the native iPhone Simulator UI test

From a clean checkout on an Apple silicon Mac with the repository's Node 24
version, CocoaPods, Xcode 26 and an installed iPhone simulator runtime, run:

```sh
npm --prefix frontend/drone/mobile ci --ignore-scripts --no-audit --no-fund
python3 -m scripts.mobile_native_compile prepare --platform ios --output "$(mktemp -d)/prepared"
scripts/ios-simulator-ui/run.sh prepare
scripts/ios-simulator-ui/run.sh test
```

Leave local port 8081 free. The test boots a fresh simulator, starts Metro for
this checkout, and launches the actual Onesa app under XCUITest. It loads the
example route, saves it to the iOS Keychain, terminates and relaunches the app,
then reopens the saved route and reads the aircraft and video status screens.
Xcode writes the test result to `frontend/drone/mobile/.validation/simulator-ui.xcresult`.
For a repeat run on the prepared checkout, set `IOS_UI_RESULTS` to a new path.

### Exercise the installed app with the real Portal issuer

Use the iOS preparation commands above and the Portal, Python and PostgreSQL
setup in [local development](../../../../docs/engineering/local-development.md#local-portal-and-drone-acceptance).
With Metro stopped, run from the Drone checkout:

```sh
.venv311/bin/python scripts/acceptance/run_local.py \
  --portal ../onesa-company-portal --pg-bin "${PG_BIN:-$(pg_config --bindir)}" --native-ui ios
```

The harness starts both products on HTTPS loopback origins and installs a
one-day certificate authority on a newly created simulator. The debug app
uses its existing development-only API setting. The test signs in an operator
and a Portal administrator in the system authentication sheet, starts separately
with an active Safari session for each role, checks their workspace or admin
authority after the OS callback, relaunches to verify Keychain persistence and
confirms global sign-out. Look for the passing XCTest count in
`frontend/drone/mobile/.validation/installed-account-summary.json`. The runner
deletes the simulator, CA and authentication result bundle after the test.

For signed-out listing images, run the separate planner test with
`IOS_UI_SCREENSHOTS="$PWD/ios-planner-images" scripts/ios-simulator-ui/run.sh test`.
It captures the actual planner and the video-unavailable screen from a fresh
simulator with synthetic local data before any identity flow runs.
