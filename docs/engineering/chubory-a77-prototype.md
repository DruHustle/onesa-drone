# CHUBORY A77 prototype assessment (2026-11-05)

## Confirmed / not confirmed

- Supplied iOS companion app ID `6467178101` is **CHUBORY FLY**, also offered on Android as `com.h8.chubory`. Public store text says it connects to F89/A77 models and offers aircraft status, flight control and video photography.
- CHUBORY advertises local Wi-Fi FPV, trajectory flight, follow-me and altitude/optical-flow functions for A77.
- **Not verified:** an open vendor SDK or protocol, authenticated GNSS/GPS coordinates, external video/RTSP/WebRTC stream, reliable cellular/cloud telemetry, autonomous waypoint upload, return-to-home semantics, transport/payload certification or a documented companion-phone integration.
- "Trajectory flight" in the manufacturer's app must **not** be conflated with GPS waypoint navigation to remote geographical locations.

The [manufacturer’s model-specific guide](https://chubory.com/pages/a77-beginner-guide) links the companion apps and operating manual.

Sources: https://apps.apple.com/app/id6467178101 ; https://play.google.com/store/apps/details?id=com.h8.chubory ; https://www.chubory.com/products/durable-brushless-motor-drone-with-84-mins-super-long-flight-time-drone-with-camera-for-beginners-chubory-a77-wifi-fpv-quadcopter-with-2k-hd-camera-follow-me-auto-hover-3-batteries-carrying-case

## Delivered software boundary

The mobile app supports route draft/edit, scenario selection (security, conservancy, farm, medical/e-commerce), encrypted local storage, route distance estimate, synthetic marker playback, operator-labelled bench and simulation notes held in-session or saved to encrypted device storage, manual safety checklist and explicit vendor-app video handoff. An A77 has no live position or live video inside Onesa until the hardware interface is qualified. Backends and edge integrations remain **simulation-only** under `AGENTS.md`.

**Never automatically launch a physical flight, operate payload releases, initiate a patrol, or infer a person's identity or location.** Do not substitute the smartphone GPS for aircraft GPS or simulate a "live" feed. Drone location telemetry, battery and camera must show unavailable if no authenticated hardware sample exists.

## Using the mobile app for a ground bench check

With the aircraft stationary and its motors off, open **Aircraft → A77 ground bench record**. Enter the aircraft's local asset label. Enter the firmware and CHUBORY FLY version if known. Unavailable versions appear as **Unknown** in the report.

The four checks cover what CHUBORY FLY displays for connection, loss and restoration of the local link, and what Onesa displays for actual aircraft position. Record **Observed** or **Issue** for each check you perform. Leave **Untested** for anything you did not check. Each result records the phone's UTC time. These entries are operator observations.

Reopen Onesa to resume the record. **Share bench record** opens the phone's share sheet with the asset, versions, timestamps and individual findings. The app holds one encrypted worksheet per device. Share any record you need to keep before confirming its deletion to start the next one. Under **Monitor → Human observations**, you can also keep free-text bench notes separate from simulation review notes.

### First supervised, stationary observation

| Step | Operator action | Evidence to record |
| --- | --- | --- |
| 1. Identify | With the aircraft off, read the aircraft and controller labels. Compare the exact A77 variant and its supplied guide with the manufacturer's guide. Record a local asset label, controller revision, phone OS, companion app version and aircraft firmware if displayed. | Photograph labels for your private record. An app version is a separate value from aircraft firmware. Enter **Unknown** if firmware is unavailable. |
| 2. Prepare | Keep the aircraft stationary on a clear, level bench. Remove propellers with power disconnected using the model's manual if supported. If safe non-actuating setup cannot be established, stop at identification. | Record the setup and who has physical control. Keep the remote and app's flight inputs untouched. |
| 3. Connect | Use the guide supplied with the matching revision. The linked A77 manual, printed page 15, identifies a Wi-Fi network whose name begins with **CBR** and the **CHUBORY FLY** app. Open only one companion app at a time. | Record the Wi-Fi association and the vendor app's own connection indication separately. If the label, guide or network differs, stop and obtain confirmation for that variant. |
| 4. Observe | From the companion app's stationary status/camera display, record exactly which values appear and their units. For a video check, point at a non-sensitive moving object to distinguish current frames from a still image. Stop if an observation would require motor activation. | Record unavailable fields explicitly. A phone location is phone data. Onesa **Monitor** should report actual aircraft position as unavailable. Vendor preview is separate from Onesa recording. |
| 5. Disconnect | While stationary, disconnect the phone from the aircraft Wi-Fi. Observe connection indication, last image/status and elapsed time. | Record UTC times and whether values cleared, froze or were marked stale. Mark **Issue** if stale information looks current. |
| 6. Reconnect | Rejoin the same network and confirm the vendor status has resumed or the camera shows a new scene. Close the app and power down according to the manual. | Record time to recovery and any unexpected action. Save each actual outcome under **Aircraft → A77 ground bench record**. |

The supported interface documented here is first-party Wi-Fi access through the vendor app. For third-party telemetry, request a manufacturer-supported read-only SDK or interface for the aircraft/controller revision and firmware, including identity, timestamp, units, disconnect behavior and which data fields can be read. Only the operator with the aircraft can complete the observations above.

[CHUBORY A77 beginner guide](https://chubory.com/pages/a77-beginner-guide) · [Operating manual, printed pages 15–17](https://cdn-files.myshopline.com/file/store/1685936101621/A77-USER-MANUAL.pdf)

### Operator action paths

| Operator action | API and process | Source of confirmation |
| --- | --- | --- |
| Register or edit fleet equipment | Web form → aircraft API → tenant-scoped database transaction | API returns the saved simulated aircraft. |
| Inspect, charge, retire or restore | Web fleet action → aircraft command endpoint → tenant lock, idempotency receipt and revision check → simulation inventory | Updated aircraft revision and simulation audit. |
| Request or plan a delivery and assign an aircraft | Web form → mission creation or mission command endpoint → stored mission or route planner → reservation | New mission, assignment, revision and mission history. Dispatch preview only proposes assignments. |
| Validate, authorize, launch, cancel, replan, reschedule or recover | Web mission controls → mission command endpoint → state machine and launch safety supervisor → simulation worker | The API acknowledges a committed command. Worker progress arrives in operations snapshots and recorded mission events and samples. |
| Inspect telemetry or replay | Web telemetry → operations snapshot/stream or mission history → selected tenant's records | Stream silence and stale mission samples are shown separately. Historical playback does not submit commands. |
| Prepare a mobile route or play a marker | Mobile Plan and Monitor → encrypted draft or local interpolation | Local UI only. No upload, aircraft telemetry or command confirmation. |
| Check camera or ground connection | Mobile Video/Aircraft → manufacturer listing / bench worksheet → operator opens CHUBORY FLY | Operator's vendor-app observation. No Onesa camera recording, command transport or A77 acknowledgement exists. |
| Pair, arm or command A77 through Onesa | No operator path. The physical edge adapter rejects connect and send. | No hardware acknowledgement possible in this release. |

Web simulation commands reference the displayed server snapshot with a 25-second deadline. A command that first reaches the server after expiry is refused. A duplicate of a committed request can return its stored acknowledgement without executing again. If the browser cannot establish whether a request committed, inspect the refreshed state or mission history before issuing another action. Reconnecting to the telemetry stream performs reads only.

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
