# iOS device archive and public distribution

Drone's bundle identifier is `eu.onesa.drone`. The separate iOS device-release check builds the `OnesaDrone` Release scheme with the `iphoneos` SDK for a generic physical arm64 device. It verifies the Mach-O platform, app identity, embedded JavaScript bundle and absence of distribution signing. CI retains no archive or IPA, and requires no Apple signing identity. The existing simulator job remains separate.

## Set up the owner release

In the approved Apple Developer team, check Certificates, Identifiers & Profiles for the explicit `eu.onesa.drone` identifier. Register it if absent. In App Store Connect, add the matching iOS app record using the owner-selected name, primary language and SKU. Use the existing approved Apple Distribution identity and matching App Store provisioning profile, or have the authorized owner provision them for this app/team. Confirm that the owner has the distribution role and that the intended marketing version and build number are accepted for this record.

On the approved Mac, use a clean checkout, the pinned Node/Expo dependencies and the release commit. Run the following from the repository root with a new build directory outside the checkout.

```sh
npm --prefix frontend/drone/mobile ci --include=dev --ignore-scripts --no-audit --no-fund
npm --prefix frontend/drone/mobile test
python3 -m scripts.mobile_native_compile prepare --platform ios --output "$DRONE_IOS_BUILD_DIR"
(cd frontend/drone/mobile/ios && pod install)
```

In the generated `frontend/drone/mobile/ios/OnesaDrone.xcworkspace`, select the approved team in the app target's Signing & Capabilities settings. For manual signing, choose that team's matching distribution profile for Release. With this configuration and its signing material already available in the owner’s keychain, create a separate signed archive.

```sh
xcodebuild -workspace frontend/drone/mobile/ios/OnesaDrone.xcworkspace -scheme OnesaDrone \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -archivePath "$DRONE_IOS_BUILD_DIR/OnesaDrone.xcarchive" archive
```

In Xcode Organizer, validate the archive and choose Distribute App → App Store Connect. For a repeatable command-line upload or export, retain the owner-approved ExportOptions plist privately with the release records. Select method `app-store-connect`, the matching `teamID`, and the signing style used to create the archive. For manual signing, use the matching distribution certificate and a `provisioningProfiles` entry for `eu.onesa.drone`. Choose `destination=upload` to upload the archive or `destination=export` for a private signed IPA. The supported keys for the installed Xcode version appear under `xcodebuild -help`.

```sh
xcodebuild -exportArchive -archivePath "$DRONE_IOS_BUILD_DIR/OnesaDrone.xcarchive" \
  -exportPath "$DRONE_IOS_BUILD_DIR/export" -exportOptionsPlist "$DRONE_EXPORT_OPTIONS_PLIST"
```

For TestFlight, wait for processing, assign the build to the external-testing group, complete the first beta review and check the enabled public invitation with a separate physical device. Confirm offline startup and that simulated telemetry and aircraft command restrictions are preserved. Use the verified public invite or published App Store URL for the website. A locally exported IPA requires the correct Apple distribution channel and provisioning to install.

- https://developer.apple.com/help/account/identifiers/register-an-app-id/
- https://developer.apple.com/help/app-store-connect/create-an-app-record/add-a-new-app/
- https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/
- https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers/

## Prepare the store record

Use the simulation companion as the store product. A suitable description is “Plan and save inspection routes, preview them in simulation, and keep a bench notebook for your aircraft. Sign in with your existing Onesa account to see your workspaces and keep your field records separate on this device.” Use actual iPhone and iPad screenshots of the planner, synthetic route replay and notebook from the release candidate. Use the account screen’s privacy and account-deletion destinations in the corresponding store fields, after verifying them from an unrelated network. Provide a dedicated approved reviewer account with synthetic data and reproducible MFA access if required for that role.

Before upload, confirm the marketing version and build number against the existing store record. Verify the signed archive in Xcode Organizer with the approved team. Review the generated privacy report and all bundled SDK manifests. The account flow sends the sign-in and session requests to the Portal and Drone services. Field drafts, positions entered by the user, notes and bench observations stay in device storage unless the operator opens the OS share sheet. This release has no camera capture, aircraft connection, ad tracking or in-app purchase. Confirm the declarations, support contact, age rating and screenshots against the signed build and the deployed services before submitting.

Install the processed build through TestFlight. On a fresh installation check device-only planning, interrupted sign-in, an existing Portal session, sign-out, account switching, private field record isolation after relaunch, the deletion request and availability of both phone and tablet layouts. Keep the signed build number and actual device/OS with the results.

- https://developer.apple.com/news/upcoming-requirements/?id=04282026a
- https://developer.apple.com/support/offering-account-deletion-in-your-app/
