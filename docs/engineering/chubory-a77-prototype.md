# CHUBORY A77 prototype assessment (2026-11-05)

## Confirmed / not confirmed

- Supplied iOS companion app ID `6467178101` is **CHUBORY FLY**, also offered on Android as `com.h8.chubory`. Public store text says it connects to F89/A77 models and offers aircraft status, flight control and video photography.
- CHUBORY advertises local Wi-Fi FPV, trajectory flight, follow-me and altitude/optical-flow functions for A77.
- **Not verified:** an open vendor SDK or protocol, authenticated GNSS/GPS coordinates, external video/RTSP/WebRTC stream, reliable cellular/cloud telemetry, autonomous waypoint upload, return-to-home semantics, transport/payload certification or a documented companion-phone integration.
- "Trajectory flight" in the manufacturer's app must **not** be conflated with GPS waypoint navigation to remote geographical locations.

Sources: https://apps.apple.com/app/id6467178101 ; https://play.google.com/store/apps/details?id=com.h8.chubory ; https://www.chubory.com/products/durable-brushless-motor-drone-with-84-mins-super-long-flight-time-drone-with-camera-for-beginners-chubory-a77-wifi-fpv-quadcopter-with-2k-hd-camera-follow-me-auto-hover-3-batteries-carrying-case

## Delivered software boundary

The mobile app supports route draft/edit, scenario selection (security, conservancy, farm, medical/e-commerce), encrypted local storage, route distance estimate, synthetic marker playback, operator-labelled bench and simulation notes held in-session or saved to encrypted device storage, manual safety checklist and explicit vendor-app video handoff. An A77 has no live position or live video inside Onesa until the hardware interface is qualified. Backends and edge integrations remain **simulation-only** under `AGENTS.md`.

**Never automatically launch a physical flight, operate payload releases, initiate a patrol, or infer a person's identity or location.** Do not substitute the smartphone GPS for aircraft GPS or simulate a "live" feed. Drone location telemetry, battery and camera must show unavailable if no authenticated hardware sample exists.

## Using the mobile app for a ground bench check

With the aircraft stationary and its motors off, open **Aircraft → A77 ground bench record**. Enter the aircraft's local asset label. Enter the firmware and CHUBORY FLY version if known. Unavailable versions appear as **Unknown** in the report.

The four checks cover what CHUBORY FLY displays for connection, loss and restoration of the local link, and what Onesa displays for actual aircraft position. Record **Observed** or **Issue** for each check you perform. Leave **Untested** for anything you did not check. Each result records the phone's UTC time. These entries are operator observations.

Reopen Onesa to resume the record. **Share bench record** opens the phone's share sheet with the asset, versions, timestamps and individual findings. The app holds one encrypted worksheet per device. Share any record you need to keep before confirming its deletion to start the next one. Under **Monitor → Human observations**, you can also keep free-text bench notes separate from simulation review notes.

## Next validated hardware steps

1. Inventory the specific A77 hardware, firmware, controller, Wi-Fi hotspot and camera stream with owner and manufacturer's documentation. Obtain an SDK/protocol specification or explicit permitted integration path. Do not guess command bytes.
2. Use a non-flying bench test to validate read-only status, connection ownership, power and telemetry source. Test disconnect/reconnect, replay/spoof protection, timestamps, and link-loss indications without arming motors.
3. If telemetry/video interfaces are supported, implement a **separate** authenticated edge gateway. Require verified aircraft identity, typed freshness/quality, transport encryption, per-user stream authorization, bounded retention and audit logs. Live aviation decisions remain supervised.
4. Select an aircraft/platform with supported flight controller/autopilot, GPS, obstacle sensing, robust failsafes, airspace data, environmental suitability and certified payload hardware for any supervised field pilot. The A77 must not be treated as automatically suitable for anti-poaching patrols or medical delivery.
5. Document appropriate CAAZ and/or EASA rules for each operating location. In the EU, ordinary open-category operations generally require VLOS, with BVLOS subject to specific-category authorization or another applicable path; carrying/dropping payloads is additionally restricted. Conduct a privacy, wildlife disturbance, and security risk assessment before any real imaging or route execution.

## Verification evidence

- Native route validation, replay and encrypted storage logic: `frontend/drone/mobile/tests/mission-core.test.mjs`.
- Web console regression: retained acceptance and release packager checks under the new source path.
- Mobile Expo JavaScript bundling: `onesa-drone/.github/workflows/verify.yml` (generates root `_verify-drone.yml`) at repository root.
- Hardware pairing, true GPS, live video, Android APK, signed iOS binary and physical safety supervisor are **not** accepted by any of these software tests.
