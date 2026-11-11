# Onesa Drone mobile field operations

iOS and Android React Native/Expo SDK 58 prototype. Production aircraft control is deliberately **disabled** by the Onesa Drone engineering policy.

## Implemented in the app

- Manual latitude/longitude waypoints with validation, distance review, interactive relative map, route editing and saved mission drafts.
- Security rounds, farm inspections, conservancy observation, medical-delivery and e-commerce-delivery planning templates.
- Local-only route simulation with positions explicitly identified as synthetic. Hardware position, battery and camera state remain unavailable without a verified source.
- Up to 12 device-local drafts in Expo SecureStore. At capacity, the planner preserves each saved route and prompts the operator to delete one before adding another. Concurrent saves and interrupted storage operations have regression coverage.
- Under **Aircraft**, a recoverable encrypted ground bench record captures the asset label, known firmware and companion-app versions, and four timestamped human observations. The operator can reopen it offline, share the record explicitly, or delete it.
- Under **Monitor**, choose a bench observation or a simulation review, then choose a session note or an encrypted note saved on this device. Each log holds ten notes and preserves existing entries when full.
- Camera panel explaining the local CHUBORY FLY Wi-Fi feed and offering an external handoff to the official companion app.
- Safety checklist and no remote flight, mission launch, take-off, payload release, human tracking, automated surveillance or live video endpoints.

## Setup and tests

```bash
cd onesa-drone/frontend/drone/mobile
npm ci --ignore-scripts --no-audit --no-fund
npm test
npx expo install --check
npm run export
npm run ios       # Mac + Xcode
npm run android   # Android SDK
```

`ios/` and `android/` contain the platform build targets; Expo prebuild generates platform-specific Xcode/Gradle source there. The Expo runtime and host OS tools are required for compiled native acceptance. The GitHub-hosted Node tests exercise planning, simulation and secure-store business rules, not physical A77 hardware.

The product verification workflow also compiles Android arm64 debug and iOS arm64
simulator targets. It generates native sources from the template inside the locked
Expo package and checks that the app configuration and package lock remain unchanged.
Native output qualification checks the application ID and compiled architecture,
then retains the exact binary and a proof binding its SHA256 to the source commit,
source trees, dependencies and toolchain. iOS uses no distribution signing or
provisioning. Its main executable may carry a linker ad-hoc signature; Apple strict
verification checks an exact, bounded copy in a temporary directory outside the
unsigned app bundle. The original executable and copy must retain identical bytes
before and after verification, and the copy is removed on success or failure.
The proof labels this executable-only verification separately from the absent Apple
bundle resource seal. The original bundle and its resources remain bound by the
existing complete file-hash tree; the build does not acquire a bundle signature.
The first resolved CocoaPods and SwiftPM locks are retained for review, not presented
as previously committed locks. A successful compile is separate from launching the
app, completing simulator journeys, signing a release, and testing a device.

## Integration boundary

The CHUBORY A77 uses CHUBORY FLY (iOS App Store ID 6467178101; Android `com.h8.chubory`). The vendor advertises Wi-Fi control, video, and trajectory flight, **not** a documented third-party SDK or authenticated GPS/RTSP telemetry endpoint. Onesa never reverse-engineers unsafe flight commands or assumes a phone location is the drone location.

A later supported aircraft adapter must authenticate telemetry, prove source/freshness, restrict video URLs and audit every access; pass supervised flight test and operator/regulatory acceptance before any physical dispatch. Long-range wildlife patrols and medical deliveries require suitable aircraft and aviation approvals and are not supported by this prototype.

No map tiles are sent to third parties: route sketches use local SVG geometry and are not airspace maps. Do not use demo coordinates as actual airspace/terrain clearances.
