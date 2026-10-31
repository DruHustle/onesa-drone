# NVIDIA reference environment

The console loads three NVIDIA SimReady derivatives automatically alongside its
existing illustrative campus and aircraft: a transfer conveyor, mobile cart and
warehouse rack. The Camera selector can frame the environment models. Orbit mode
supports pointer interaction and arrow-key pan while the canvas has keyboard focus.
Source details and static previews are available under the scene.

All asset requests are local to the application. The independent asset package is
under `frontend/public/models/nvidia`; no other Onesa repository, external model CDN,
NVIDIA installation, model-service account or GPU-specific runtime is required.
The executable catalogue in `frontend/src/nvidia-manifest.json` is a byte-preserving
copy of the public manifest; a test requires its asset entries to agree exactly.

## Provenance and license

The source is NVIDIA's `nvidia/simready-assets` dataset, fixed to revision
`4763fbfaa4f8e97658e68b57d01b4c86659e08b5`. Each asset directory retains its own
`SOURCE.json` and CC BY 4.0 `LICENSE.txt`, including the original source paths and
the conversion/simplification/material-adaptation record. The application exposes
the attribution, original source, license and provenance without requiring a 3D
render. Attribution does not imply NVIDIA endorsement. The asset license does not
assign a new license to Onesa's application code.

The three compact GLBs total 3,874,632 bytes and 87,251 triangles. Their reviewed
files have no external resource URIs, extensions, animation, skins or active content.
Each runtime fetch omits credentials, refuses redirects, has a 15-second deadline,
stops at the exact declared size and verifies SHA-256 before parsing. A damaged or
unavailable model cannot silently replace the pinned reference.

## Rendering and operational boundaries

The model locations and scale are illustrative scene choices. Reference props never
enter the mission plan, collision supervisor, launch policy, telemetry, sensor state
or aircraft adapter. Importing or viewing them does not write operational records or
enable any physical transport. Existing flight/replay controls and low-power,
reduced-motion, day/night and weather choices remain available.

Loading is asynchronous. The procedural scene renders first, completed references
appear independently and failed references keep their static previews and retry.
Leaving a scene cancels outstanding downloads and disposes GPU resources. A lost
graphics context shows the same rendered model previews; restoration rebuilds the
scene, and a manual retry is available. Browsers without WebGL can use the previews,
source details, mission controls and telemetry without an empty viewer.

Verification results and remaining release gates are recorded in
[verification.md](verification.md). A local render or merged source does not itself
establish hosted acceptance, hardware behaviour or physical-flight authorization.
