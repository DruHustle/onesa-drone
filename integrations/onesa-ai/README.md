# Portable AI advisory integration

Implementation: `integrations/onesa_ai/adapter.py`, with the independently vendored
`integrations/ai/consumer.py` transport. The same assistant workflow can use Onesa
or a compatible provider by changing server configuration. No business workflow,
mission record, safety supervisor, launch permission or embedding index changes.

| `ONESA_AI_PROVIDER` | Contract and credentials |
| --- | --- |
| `onesa-legacy` (default) | Existing owned-conversation/session API. Preserves existing deployments; requires an explicit successful stream end. |
| `onesa` | `onesa-inference-v1`, using the AI service origin, dedicated session, Origin and CSRF. The AI server must separately enable its consumer endpoint. |
| `openai-compatible` | Text Chat Completions subset: approved HTTPS `/v1` base, server bearer credential, configured model; nonstreaming complete text only. |
| `disabled` | Explicitly labelled deterministic local summary; no provider request. |

Common private server settings are `ONESA_AI_URL`, `ONESA_AI_MODEL` and
`ONESA_AI_TENANT_ID`. Onesa additionally requires `ONESA_AI_ORIGIN`,
`ONESA_AI_DELEGATED_SESSION` and `ONESA_AI_DELEGATED_CSRF`. A compatible provider
requires its separately approved `ONESA_AI_API_KEY`; it never receives Onesa cookies
or CSRF. Endpoints reject HTTP, embedded credentials, queries and fragments. Redirects,
inherited proxies, automatic provider retries and cross-provider fallback are disabled.
The delegated identity/credential is mapped to one exact tenant; another tenant uses
the explicit local summary without contacting either provider. Known provider/model/
revision/usage remain attached to each result, without claiming unknown token counts.

This transport is a reviewed source copy of AI Platform `app/consumer.py`, SHA256
`48ff4e7f5a48deb46385a5ae8239cd5bea50c55e227846846ff6666829f98378`.
Builds use only local bytes and locked httpx; no sibling package or shared runtime is
imported. Updates need a new inspected copy/hash, independent checks and rollback.

The portable records are a bounded list of `{role, content}` messages and a complete
text result with provenance. Unsupported tool calls, truncation, malformed JSON,
oversize responses, excessive JSON nesting and failed streams do not become advice.
Malformed or excessively nested JSON in both portable responses and legacy stream
records returns the explicit unavailable-provider summary without exposing the body.
The 25-second total
budget includes connection and response reads. Failure returns the clearly labelled
existing local summary; it never sends data to another AI provider. Names, routes,
recipient tokens and user identifiers are omitted from the operational context.

MCP is a separate tool/context boundary. AI Platform's optional local stdio bridge
currently exposes only explicitly allowed arithmetic/text-statistics tools. This
Drone adapter registers no MCP mission or aircraft tools, and model text cannot
authorize, mutate or launch a mission. Robot/Drone safety stays independent.

Do not reuse a human owner's session. Commission a dedicated, approved identity and
validate expiry/revocation, data processing and provider retention before connecting.
The portability and failure tests use synthetic HTTP responses; neither provider,
credentials nor a live model is activated by this source change. External-client,
staging and hosted acceptance remain independent release requirements.
