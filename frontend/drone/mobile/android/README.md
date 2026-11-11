# Android builds

The Expo app lives one directory above this target. For development, install the
locked mobile dependencies, generate the Android project with Expo prebuild, then
run `npm run android` with the Android SDK and an emulator or phone.

## Offline A77 bench build

The **Android bench APK** workflow builds a separate arm64 app named **Onesa Drone
Bench**, with the application ID `eu.onesa.drone.bench`. It embeds the mobile app
in the APK so the operator can reopen the worksheet with the phone offline or on
the aircraft's local Wi-Fi. It uses a development test certificate and a separate
data store from the public app. Its separate native entry opens the device-only
planner. The bench build handles `onesadrone-bench` links. The store release
handles `onesadrone://account/callback` for Portal sign-in, so both editions can
stay installed on one phone.

Select a successful workflow run for the intended commit and download its
artifact. Extract `OnesaDrone-arm64-bench.apk` and `compile-proof.json` together.
The proof identifies the source revision, signer, embedded bundle and APK SHA-256.
For an Android phone with USB debugging enabled and connected to your workstation:

```sh
adb install -r OnesaDrone-arm64-bench.apk
```

Open **Onesa Drone Bench → Aircraft → A77 ground bench record**. With the motors
off, save the asset label and the observations you can verify. Reopen the app
with the phone offline and check that the saved record and its timestamps survive.
The ground worksheet and the companion-app observations are described in the
[A77 assessment](../../../../docs/engineering/chubory-a77-prototype.md).
