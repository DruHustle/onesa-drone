# Installed iPhone qualification

The hosted account, debug planner and standalone Release planner jobs use Xcode
26.6, the installed iOS 26.4.1 runtime and iPhone 17 Pro device type. This is the
pairing that completed strict boot readiness and the real standalone planner test
in [run 43862391469](https://github.com/DruHustle/onesa-drone/actions/runs/43862391469).
The default highest-runtime selection subsequently failed OS migration twice in
[account job 133282252846](https://github.com/DruHustle/onesa-drone/actions/runs/43862391407/job/133282252846),
before the application or account fixture was reached. A different runtime is a
separate qualification choice, not an automatic fallback.

`select_simulator.py` resolves the configured version from `simctl list runtimes`
and requires its available iPhone pairing in `simctl list devices`. A runtime's
identifier can say `iOS-26-4` while its actual version is `26.4.1`; selection checks
the version metadata. Missing or partial configuration fails without downloading
another runtime. CI sets both `ONESA_IOS_UI_RUNTIME_VERSION` and
`ONESA_IOS_UI_DEVICE_TYPE`. Local development may omit both to exercise its newest
installed iPhone/runtime; the actual selection is printed and retained in the
account receipt, and does not substitute for hosted qualification.

`boot.py` requires a terminal successful boot, since `simctl bootstatus` can return
zero even when data migration fails. Setup may replace its own fresh simulator
once before installing any certificate or application. Failure to boot the second
device fails the job. There is no retry of a failed account or planner test, and
exactly one successful required XCTest with zero failed/skipped tests is required.
No physical device, aircraft interface, provider or production account is used.

Both Debug UI paths compile and verify the complete Metro entry response before
launching XCTest. A listening `/status` endpoint alone does not establish bundle
readiness. Both profiles require the debug account module. The planner profile
also requires its offline planner labels; the account profile requires the exact
loopback fixture origin. Both retain the 120-second preparation bound, response size/type
checks and redirect/proxy refusal. Only fixed metadata and a digest leave the
preflight. The actual UI, encrypted-draft persistence and hardware-lock assertions
remain independent and keep their original deadlines. Standalone Release still
runs its bundled application without Metro.

The Debug test build disables the compiler index store to keep disposable editor
index records from exhausting runner storage. All source compilation and the
complete selected XCTest remain required. The hosted Debug planner boots its
fresh simulator before the standalone native compile proof, matching the startup
order that passed in the Release planner. The generic arm64 build and its
provenance checks still run before producing combined Debug evidence.

The harness checks SpringBoard's localhost sign-in alert before and after each
browser accessibility lookup. Once the alert appears, it gives the exact enabled,
hittable Continue control ten seconds to become actionable. Each tap uses that
control's current frame, bounded by the verified alert and foreground application.
The harness permits one repeat only while the same consent is present. Portal
must appear after the alert is dismissed. Fixed tapped, retried and dismissed
checkpoints distinguish a retained OS prompt from a missing issuer form.
Preparation refreshes both copied XCTest sources even when the generated native
target already exists, so repeated local qualification runs use current helpers.

WebKit may expose an embedded authentication form outside the first web view,
with HTML labels as neighbouring text nodes. The account suite checks all active
browser surfaces and accepts an owning-app form only while the Safari service is
running and the exact Portal heading, remember control and cancel action are
present. Unnamed inputs must have a unique type in that verified form; after MFA
adds another text input, the previously entered fixture email must remain unique
by its exact value. Keyboard input is verified before submission, including the
secure-field length. Member/admin cold and warm sign-in, MFA, issuer request
counts, scoped expiry, immutable subject, Keychain relaunch and logout checks all
remain mandatory. Only fixed failure-state flags leave the private test output.
If a receipt read times out, loses its connection, or cannot connect, the suite
reads it once more after a short pause. It still requires exact issuer counts.
It never retries the session-expiry POST or replays credentials on a read error.

The private log also records fixed browser owner states, semantic consent presence,
native touch completion, WebView query progress/counts and expected issuer landmark
presence. The public reducer retains at most 64 observations and rejects unknown
names and out-of-range values. Counts saturate at eight. Navigation values mean
waiting (0), before consent touch (1), consent dismissed (2), and failed wait (3).
No observed text, URL, hierarchy, screenshot or error description is published.
When the verified OS consent prompt remains visible, failure reporting does not
query the covered browser tree; the original account assertion still fails.
