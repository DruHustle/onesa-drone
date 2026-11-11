# Distribute the simulation companion

The Android/iOS app is `eu.onesa.drone`. Its Expo configuration disables hardware flight and labels positions as simulated. The owner can release this companion independently of the web console. A CI debug APK, emulator build, unsigned file or manufacturer’s companion does not qualify as an install link.

## Prepare an Android release

Use a clean checkout of the exact owner-reviewed standalone release commit on a workstation with Node 24.22.1, Python 3.11+, JDK 17 and the Android SDK. Set `ANDROID_HOME` and `JAVA_HOME`. Install Android platform 37.0, Build Tools 37.0.0, and NDK 27.1.12297006. Where the SDK provides only `platforms/android-37.0`, apply the integer alias `platforms/android-37` used by the native CI job. Keep the signing key outside the source checkout, CI and build directory. For an update, select the same approved signing lineage as the installed app and increase the Android versionCode in the reviewed Expo configuration before building.

```sh
npm --prefix frontend/drone/mobile ci --ignore-scripts --no-audit --no-fund
npm --prefix frontend/drone/mobile test
python3 -m scripts.mobile_android_distribution build --directory "$DRONE_RELEASE_DIR"
```

Choose a new private `DRONE_RELEASE_DIR` outside the checkout. The build uses the locked Expo template and Gradle distribution, removes the template’s release signing configuration, builds arm64 with the JS bundle embedded, and aligns the APK. The private receipt binds the version, source commit and every APK member. Keep the unsigned output on the workstation for the signing step.

## Sign and verify

Set `DRONE_RELEASE_KEYSTORE` and `DRONE_RELEASE_KEY_ALIAS` to the approved owner signing reference. Obtain `DRONE_RELEASE_CERT_SHA256` independently from the owner's existing signer record or Android app-signing console. The APK served directly on the website must use the app distribution key; Google Play's upload key may be a different key. Supply passwords only at apksigner's prompt. An existing managed/HSM signing flow can perform the equivalent APK v2/v3 signing operation without exporting key material.

```sh
"$ANDROID_HOME/build-tools/37.0.0/apksigner" sign \
  --ks "$DRONE_RELEASE_KEYSTORE" --ks-key-alias "$DRONE_RELEASE_KEY_ALIAS" \
  --v1-signing-enabled false --v2-signing-enabled true --v3-signing-enabled true \
  --out "$DRONE_RELEASE_DIR/signed.apk" "$DRONE_RELEASE_DIR/aligned-unsigned.apk"
python3 -m scripts.mobile_android_distribution verify \
  --directory "$DRONE_RELEASE_DIR" --apk "$DRONE_RELEASE_DIR/signed.apk" \
  --certificate-sha256 "$DRONE_RELEASE_CERT_SHA256" --url "$DRONE_PUBLIC_APK_URL"
```

The verifier checks the installed Android signing tool’s result, exactly one authorized release certificate, APK alignment, non-debuggable package and version, the embedded React Native bundle, the source receipt, and complete payload equality with the unsigned candidate. For the current 0.1.0 version, the allowed GitHub release layout is tag `mobile-v0.1.0` with asset name `onesa-drone-android-v0.1.0.apk`. The Onesa product-host layout is `/downloads/onesa-drone-android-v0.1.0.apk` on `drone.onesa.eu`. Use the same version convention for a subsequent release. These names describe destinations for an approved upload.

Install the signed candidate on a supported arm64 device. Test a cold start offline, draft create/reload, simulation and disabled aircraft controls. Publish the signed bytes to the approved destination, retrieve its public bytes as a visitor and verify the SHA-256 against the verifier output. Add its emitted object (`url`, `sha256`, `certificateSha256`, `sourceCommit`) as `android` in `frontend/drone/web/src/mobile-downloads.json`. A verified Google Play listing can alternatively be configured as a store URL. Keep the other platform’s status independent.

## iOS release and public beta

Use the existing Apple Developer team and its `eu.onesa.drone` identifier, distribution certificate and provisioning profile. From the clean checked-out mobile source and installed dependencies, run `python3 -m scripts.mobile_native_compile prepare --platform ios --output "$DRONE_IOS_BUILD_DIR"` from the repository root. Install Pods for the generated native project and open `frontend/drone/mobile/ios/OnesaDrone.xcworkspace` in Xcode. With that team, select a generic physical iOS destination, create a Release archive, validate it and upload it to the matching App Store Connect app. Complete the owner’s device checks. For a beta, assign the approved external-testing build to its TestFlight group and check its public invitation on a separate device. For a store release, check the published entry. Enter the actual Apple Store or public TestFlight URL under `ios` only after those observations.

The official tool references cover Android signing and alignment, plus Apple’s external tester process.

- https://developer.android.com/tools/apksigner
- https://developer.android.com/tools/zipalign
- https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers
