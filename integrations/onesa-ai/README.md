# Onesa AI integration

Implementation: `integrations/onesa_ai/adapter.py` (Python import conventions).
It uses the inspected Onesa Platform `/api/v1/conversations` and
`/api/v1/chat/completions` API with session cookie, Origin and CSRF. The delegated
identity is explicitly mapped to one Drone tenant; other tenants use the labelled
local summary. No mission mutation or flight tool is registered.

Optional settings are server-only: ONESA_AI_URL, ONESA_AI_ORIGIN,
ONESA_AI_DELEGATED_SESSION, ONESA_AI_DELEGATED_CSRF, ONESA_AI_TENANT_ID.
Do not reuse a human owner's session. Commission a dedicated, approved identity and
validate expiry/revocation, data processing and provider retention before connecting.
The automated contract test uses an HTTP mock. No live model or integration identity
has been exercised. The local assistant is a deterministic summary, not a model.
