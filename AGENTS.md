# Onesa Drone engineering policy

This product lives in the standalone `DruHustle/onesa-drone` repository. Preserve
independent builds, releases, API authorization, data and runtime dependencies; do not
create nested Git repositories or sibling submodules. Run product commands from
this repository root. Its root workflows execute all product and native compile
checks. Use dev → staging → main with PRs and exact-source checks.
Preserve concurrent work and data. No paid resources without budget approval.
No license is assigned. Credentials, customer records and private deployment bundles
must never enter Git or CI artifacts. Use synthetic fixtures and inspect staged diffs.

Simulation is the only permitted execution mode. Do not enable physical flight,
network MAVLink, hardware serial, ROS actuation or generative AI mission authorization.
The separate safety supervisor must validate every launch. Simulation, replay and
real observations must remain distinct. A visual twin is not validated flight physics.

Use Node 24 and Python 3.11. Run backend tests, frontend typecheck/build, browser
checks and `python3 scripts/repository_hygiene.py` before staging. Record actual results and
unverified gates. Pin dependencies and design artifacts; no runtime sibling imports.
Appearance follows prefers-color-scheme only. Respect reduced motion and forced colors.

Production requires checked source, staging acceptance, provider readback, rollback,
privacy review and owner authorization. Never bypass protection or invent approval.

## Local work and verification

Keep extra checkouts under `local-tools/worktrees`, provider receipts under
`local-tools/deployment-evidence`, verification scripts and logs under
`local-tools/release-verification`, and migration records under
`local-tools/migrations`. Do not create workspace-root evidence directories.
Inspect current open PRs and remote refs before implementing overlapping work.
Portal acceptance covers the legacy issuer during migration. The managed pilot uses
Onesa Identity at `auth.onesa.eu` for human sign-in and product grants. Verify the
Drone API audience and signed stable Onesa ID. Drone owns workspace memberships,
resource permissions and device authentication. Qualify managed web/native sign-in
and simulation recovery separately; source does not establish deployment.
Use locked Python 3.11 requirements and the Node 24 frontend lockfile. Local
socket/browser tests require loopback access. SQLite results do not replace the
separate PostgreSQL run, native compilation, signed release or device evidence.
On the current Mac, Xcode exists at `/Applications/Xcode.app` even when
`xcode-select` points to CommandLineTools; inspect `DEVELOPER_DIR` first.
Android Studio's bundled JBR and the Android SDK exist outside the default PATH.
Toolchain discovery does not establish signing custody or connected hardware.
The next supported A77 bench activity is supervised identification and conditional
manufacturer-app, motors-off observation. No manufacturer-supported Onesa command
interface or validated aircraft firmware is established; retain the simulation-only
physical adapter and operator control of any later physical testing.
