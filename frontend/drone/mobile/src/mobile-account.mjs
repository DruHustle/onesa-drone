// The system browser owns the Portal login. Only the app receives the transaction proof.
export const CALLBACK = "onesadrone://account/callback";
export const SESSION_KEY = "onesa.drone.mobile-session.v1";
export function apiOrigin(development, configured) {
  if (!development || !configured) return "https://drone.onesa.eu";
  const url = new URL(configured);
  if (
    !["127.0.0.1", "localhost", "10.0.2.2"].includes(url.hostname) ||
    !["https:", "http:"].includes(url.protocol) ||
    url.origin !== configured
  )
    throw Error("Use a loopback development origin.");
  return url.origin;
}
const development = typeof __DEV__ !== "undefined" && __DEV__;
const API =
  apiOrigin(development, process.env.EXPO_PUBLIC_DRONE_DEV_ORIGIN) +
  "/api/v1/auth/mobile";
const STATE = /^mobile_[a-zA-Z0-9_-]{43}$/;
const PROOF = /^[a-zA-Z0-9_-]{43}$/;

export async function requestAccount(
  path,
  { body, session, method = "GET" } = {},
) {
  const controller = new AbortController();
  const deadline = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(API + path, {
      method,
      credentials: "omit",
      redirect: "error",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(session ? { Authorization: "Bearer " + session } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) {
      const error = new Error(
        response.status === 401 || response.status === 403
          ? "Your Onesa session or workspace access has changed. Sign in again."
          : "Drone account service is unavailable. Try again when connected.",
      );
      error.status = response.status;
      throw error;
    }
    return await response.json();
  } finally {
    clearTimeout(deadline);
  }
}

export async function signIn(openBrowser, request = requestAccount) {
  const start = await request("/start", { method: "POST" });
  const issuer = new URL(start.authorization_url);
  if (
    (issuer.protocol !== "https:" &&
      !(
        development &&
        issuer.protocol === "http:" &&
        ["localhost", "127.0.0.1", "10.0.2.2"].includes(issuer.hostname)
      )) ||
    issuer.username ||
    issuer.password ||
    !STATE.test(start.state) ||
    !PROOF.test(start.proof)
  )
    throw Error("Invalid sign-in response.");
  const result = await openBrowser(issuer.href, CALLBACK);
  if (result.type !== "success")
    throw Error("Sign-in was cancelled. You can start again.");
  const back = new URL(result.url);
  if (
    back.protocol !== "onesadrone:" ||
    back.host !== "account" ||
    back.pathname !== "/callback" ||
    back.username ||
    back.password ||
    back.hash ||
    back.searchParams.getAll("state").length !== 1 ||
    back.searchParams.get("state") !== start.state
  )
    throw Error("Sign-in could not be confirmed. Start again.");
  const codes = back.searchParams.getAll("code");
  if (
    back.searchParams.has("error") ||
    codes.length !== 1 ||
    !codes[0] ||
    codes[0].length > 4096
  )
    throw Error("Sign-in was interrupted. Start again.");
  const { session } = await request("/exchange", {
    method: "POST",
    body: { state: start.state, proof: start.proof, code: codes[0] },
  });
  if (!STATE.test(session)) throw Error("Drone could not establish a session.");
  return session;
}

export function privateStore(store, scope) {
  if (!/^[a-f0-9]{64}$/.test(scope))
    throw Error("Invalid account storage scope.");
  const prefix = "account." + scope + ".";
  return {
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: store.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    getItemAsync: (key, options) => store.getItemAsync(prefix + key, options),
    setItemAsync: (key, value, options) =>
      store.setItemAsync(prefix + key, value, options),
    deleteItemAsync: (key, options) =>
      store.deleteItemAsync(prefix + key, options),
  };
}
