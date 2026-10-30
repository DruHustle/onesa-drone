let csrf = "";
let sessionGeneration = 0;
export class SessionChangedError extends Error {
  constructor() {
    super("Session changed; previous response ignored.");
    this.name = "SessionChangedError";
  }
}
export function setCSRF(value: string) {
  sessionGeneration++;
  csrf = value;
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  idempotency?: string,
): Promise<T> {
  const generation = sessionGeneration;
  const response = await fetch("/api/v1" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(method === "GET" ? {} : { "X-CSRF-Token": csrf }),
      ...(idempotency ? { "Idempotency-Key": idempotency } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(25000),
  });
  if (generation !== sessionGeneration) throw new SessionChangedError();
  const data = await response.json();
  if (generation !== sessionGeneration) throw new SessionChangedError();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request rejected (${response.status})`,
    );
  return data;
}
