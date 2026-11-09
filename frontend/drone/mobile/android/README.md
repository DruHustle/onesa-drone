# Android native target

The cross-platform Expo app lives one directory above this target. Run `npm ci --ignore-scripts --no-audit --no-fund`, then `npx expo prebuild --platform android` to generate Gradle sources here. Run `npm run android` with Android SDK and an emulator/device.

The A77 is **not** paired to this app. Android Keystore encrypts locally stored mission drafts. Live GPS, camera relay, signed APK and device acceptance remain unverified release gates.
