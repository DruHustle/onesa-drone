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
