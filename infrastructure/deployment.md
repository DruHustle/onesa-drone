# Deployment and cost boundaries

The application is simulation-only. No physical network, ROS, PX4 or MAVLink
actuation endpoint exists. Native automatic Vercel deployment is disabled.

Candidate topology: static React frontend on the existing approved commercial-use
host, same-origin authenticated `/api/v1` ingress to a single 256 MiB backend on the
existing approved backend infrastructure, and an independent PostgreSQL database.
The provided Vercel manifest prepares SPA routing and security headers; `/api` must
be routed to the approved backend by the hosting ingress before any deployment.
No backend address, DNS record or reverse proxy is invented in source.

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
Only qualify an immutable reviewed source/image; the actual external owner-controlled
release verifier, environment, frontend project, backend ingress, secrets and database
have not been commissioned for this new product. Existing Portal/AI/Robot permissions
are not a new Drone deployment identity. Obtain the protected Onesa release guide
and preserve its source provenance before host operations.

Private GitHub branch protection readback returned HTTP 403 (current plan limitation).
The aggregate Actions billing readback also lacked the required user scope; hosted
validation is opt-in behind `ONESA_PRIVATE_HOSTED_VALIDATION_ENABLED` and remains
disabled until included allowance/spend controls are verified. A skipped job is not
a passing verification. Repository privacy was preserved; no upgrade, public visibility or billing change was
made. Written PR discipline is not native protection. A qualified equivalent release
control or an approved eligible plan is required before production promotion.

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
must remain within included allowance with paid usage stopped; no artifact uploads or
cache storage are configured. See [GitHub included usage](https://docs.github.com/en/billing/reference/product-usage-included).

Do not assume Vercel Hobby permits this commercial product: its
[documented policy](https://vercel.com/docs/plans/hobby) restricts it to personal,
non-commercial use. Reuse an approved eligible existing plan or choose an approved
commercial-use host; no upgrade or trial is authorized here. PostgreSQL storage,
backup, egress and compute must fit approved existing capacity/free allowances before
provisioning. No new Neon project or database was created. Hosted monthly cost cannot
be verified until the actual environment and its current allowance/headroom are read
back. This is a zero-new-spend implementation, not a promise of zero operating cost.
