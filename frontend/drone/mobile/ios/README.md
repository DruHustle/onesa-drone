# iOS native target

This Expo/React Native application is developed at the `../` root. Run `npm ci --ignore-scripts --no-audit --no-fund`, then `npx expo prebuild --platform ios` to generate the Xcode workspace inside this directory. Use `npm run ios` on macOS with a supported Xcode installation.

The A77 is **not** paired to this app. There is no CHUBORY SDK or supported remote GPS/video interface in this project. Apple Keychain backs encrypted route drafts. Native build, signing, TestFlight, simulator acceptance and device testing are release gates, not claims of completion.
