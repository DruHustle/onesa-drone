# iOS native target

This Expo/React Native application is developed at the `../` root. Run `npm ci --ignore-scripts --no-audit --no-fund`, then `npx expo prebuild --platform ios` to generate the Xcode workspace inside this directory. Use `npm run ios` on macOS with a supported Xcode installation.

The A77 is **not** paired to this app. There is no CHUBORY SDK or supported remote GPS/video interface in this project. Apple Keychain backs encrypted route drafts. Native build, signing, TestFlight, simulator acceptance and device testing are release gates, not claims of completion.

## Ground bench trial on an iPhone

On a Mac with Xcode, prepare the iOS project in a fresh checkout as described above. Use an Apple development team authorized for the app identifier and a connected development-enabled iPhone. From the mobile directory, run `npx expo run:ios --configuration Release --device` to embed the JavaScript and select the phone. The CI artifact targets the arm64 simulator. An iPhone bench trial requires its own device-signed build.

Open **Aircraft → A77 ground bench record**, save an observation, close the app, and reopen it offline to verify Keychain persistence on the handset.
