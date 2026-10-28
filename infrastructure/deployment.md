# Deployment and cost boundaries

The application is simulation-only. No physical network, ROS, PX4 or MAVLink
actuation endpoint exists. Native automatic Vercel deployment is disabled.

Owner-selected topology: static React frontend on Vercel, same-origin authenticated
`/api/v1` ingress through separate exact-host Cloudflare tunnels to Oracle, and an
independent PostgreSQL database per environment. `scripts/vercel_package.mjs` creates
source-bound prebuilt output with security headers and explicit API routing before
the SPA fallback. Production and staging cannot share an API origin or database.

The Dockerfile pins the official Python base digest, runs as UID 10001 and the
Compose candidate binds only loopback with read-only filesystem, dropped capabilities,
0.5 CPU, 256 MiB and 64 PIDs. Database/offload execution is capped at four threads and synchronous API work at
eight; async liveness does not wait for a database thread. One API/worker process is mandatory; no distributed
worker lease has been qualified. PostgreSQL pool: 3 connections + 2 overflow with
five-second acquisition timeout. An idle worker closes pooled connections and waits for an authenticated mission
command rather than polling an idle scale-to-zero database. SSE: 32 connections, one snapshot per second,
300-second reconnect window and session revalidation. Telemetry retains the last
600 samples per mission. Audit/mission records are retained; production archival and
privacy retention remain approval items. No deletion worker is enabled for real data.

Apply schema 0001 with a dedicated migrator identity. Runtime startup verifies the
source fingerprint and refuses incompatible migrations. `postgres-roles.sql` provides
a restricted no-login role; provision login secrets externally and test grants.
Use HTTPS and `COOKIE_SECURE=true`; remote database TLS must verify the provider CA.
The application refuses hosted SQLite or insecure hosted session configuration.

## Staging and promotion

Use independent dev → staging → main PRs. Hosted Actions have no runtime secrets or
production credentials. Never execute untrusted artifacts on the company host.
Only qualify an immutable reviewed source/image. The copied and independently tested
owner evidence bridge requires a separately commissioned Drone profile, pinned runners,
fresh first-attempt main CI and actual hosted observations. Existing Portal/AI/Robot
permissions are not a Drone release identity. Obtain the protected Onesa release guide
and preserve its source provenance before host operations. A prepared installation
or test fixture never constitutes hosted acceptance.

Private GitHub branch protection readback returned HTTP 403 (current plan limitation).
The aggregate Actions billing readback also lacked the required user scope and
no accessible browser session was available for a read-only alternative. The owner
subsequently confirmed included-only usage with paid overages blocked; hosted
validation was enabled and read back behind `ONESA_PRIVATE_HOSTED_VALIDATION_ENABLED`.
The selected local staging/release bundle location is `local-tools/onesa-drone`.
This does not commission a public hosting project. A skipped job is not
a passing verification. Repository privacy was preserved; no upgrade, public visibility or billing change was
made. Written PR discipline is not native protection. A qualified equivalent release
control or an approved eligible plan is required before production promotion.

## Owner-selected local staging

On 28 October 2026 the owner selected `local-tools/onesa-drone` in the Onesa workspace.
That private, ignored bundle serves the simulation at `http://127.0.0.1:3470` using
the tested `530ef50` application source. Its release manifest binds the source archive,
frontend hashes and immutable API/proxy/database images. Local operator credentials
remain in `private/operator.json`; no password is built into the repository.

From that directory, `python3 stage.py start`, `status` and `stop` manage only the
new local services. Stop preserves their dedicated PostgreSQL volume. All three
services run without root and with read-only root filesystems, bounded memory and
separate runtime/migrator database identities. Database and API have no host ports;
the proxy publishes loopback only. Local HTTP is the explicit development transport
allowance, not evidence for public HTTPS or remote verified database TLS.

Actual staged delivery, browser, runtime-grant and isolated restore checks pass.
The API, patched proxy and nonroot database scans have no HIGH/CRITICAL findings.
The bundle retains failed scan reports and prior manifest provenance. No public
hosting, production identity, DNS, provider rollout or commercial service was created.

## Backup, recovery and rollback

Before hosted release: enable access-controlled encrypted PostgreSQL backups, define
RPO/RTO with the owner, and execute a restore into a new isolated database. Verify
schema fingerprint, tenant counts, audit chain and mission checkpoints before ingress
activation. Never overwrite the current database to demonstrate a restore.

Retain the preceding frontend artifact, backend image digest and compatible schema.
Stop the old simulation worker before starting its replacement. Interrupted execution
resumes from persisted ticks; downtime advances no simulated position. On failure,
restore prior ingress/artifacts with the retained database only if schema-compatible.
Otherwise use the isolated tested restore and obtain explicit recovery authority.
Partial provider rollout and hosted restore are unexecuted gates, not successful tests.

## Cost assessment

No paid cloud resource, AI invocation or subscription was provisioned. Local runtime,
Docker fixtures and repository creation introduced no new paid service. GitHub Actions
must remain within included allowance with paid usage stopped. CI uploads two small,
credential-free component provenance manifests with one-day retention after tests and
scanning pass; no images or private deployment bundle enter CI artifacts. See
[GitHub included usage](https://docs.github.com/en/billing/reference/product-usage-included).

The owner explicitly selected DruHustle’s projects after being informed that Vercel Hobby’s
[documented policy](https://vercel.com/docs/plans/hobby) restricts it to personal,
non-commercial use. That selection does not establish commercial-use eligibility;
no paid upgrade, trial or eligibility attestation is authorized. PostgreSQL storage,
backup, egress and compute must fit approved existing capacity/free allowances before
provisioning. No new Neon project or database was created. Hosted monthly cost cannot
be verified until the actual environment and its current allowance/headroom are read
back. The Oracle candidate caps each database at 192 MiB and API at 256 MiB, binds
only loopback, and builds/scans images off-host. It preserves existing workloads,
requires 4 GiB disk and 1 GiB available-memory reserve, and creates no VM, paid backup
service or public listening port. This is a zero-new-spend implementation, not a promise
of zero operating cost. Public commercial launch and hosting-plan suitability remain
separate from a simulation deployment.
