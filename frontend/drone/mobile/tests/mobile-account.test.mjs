import test from "node:test";
import assert from "node:assert/strict";
import { CALLBACK, privateStore, signIn } from "../src/mobile-account.mjs";

const state = "mobile_" + "x".repeat(43);
const session = "mobile_" + "y".repeat(43);
const proof = "z".repeat(43);
function provider() {
  const requests = [];
  const request = async (path, options) => {
    requests.push([path, options]);
    return path === "/start"
      ? { state, proof, authorization_url: "https://portal.onesa.eu/authorize" }
      : { session };
  };
  return { requests, request };
}
test("the system browser returns to a proof-bound native exchange", async () => {
  const { request, requests } = provider();
  const browser = async (url, callback) => {
    assert.equal(url, "https://portal.onesa.eu/authorize");
    assert.equal(callback, CALLBACK);
    return {
      type: "success",
      url: CALLBACK + "?state=" + state + "&code=one-use",
    };
  };
  assert.equal(await signIn(browser, request), session);
  assert.deepEqual(requests[1][1].body, { state, proof, code: "one-use" });
});
test("interruption, wrong callback, duplicate code and changed state discard the exchange", async () => {
  for (const result of [
    { type: "cancel" },
    { type: "success", url: "https://example.test/?state=" + state },
    {
      type: "success",
      url: CALLBACK + "?state=" + state + "&code=first&code=second",
    },
    { type: "success", url: CALLBACK + "?state=unknown&code=test" },
  ]) {
    const { request, requests } = provider();
    await assert.rejects(signIn(async () => result, request));
    assert.equal(requests.length, 1);
  }
});
test("existing device drafts and each Portal subject use separate stable storage", async () => {
  const data = new Map([["draft", "device-only"]]);
  const store = {
    getItemAsync: async (key) => data.get(key),
    deleteItemAsync: async (key) => data.delete(key),
    setItemAsync: async (key, value) => data.set(key, value),
  };
  const one = privateStore(store, "a".repeat(64));
  const two = privateStore(store, "b".repeat(64));
  await one.setItemAsync("draft", "private");
  assert.equal(await two.getItemAsync("draft"), undefined);
  assert.equal(await store.getItemAsync("draft"), "device-only");
  assert.equal(
    await privateStore(store, "a".repeat(64)).getItemAsync("draft"),
    "private",
  );
});

test("release account origin is fixed and device-only storage options survive scoping", async () => {
  const { apiOrigin } = await import("../src/mobile-account.mjs");
  assert.equal(
    apiOrigin(false, "http://localhost:3400"),
    "https://drone.onesa.eu",
  );
  assert.equal(apiOrigin(true, "http://10.0.2.2:3400"), "http://10.0.2.2:3400");
  assert.throws(() => apiOrigin(true, "https://example.test"));
  const received = [];
  const scoped = privateStore(
    {
      WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
      setItemAsync: (...args) => received.push(args),
    },
    "a".repeat(64),
  );
  await scoped.setItemAsync("bench", "record", {
    keychainAccessible: scoped.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  assert.deepEqual(received[0].slice(1), ["record", { keychainAccessible: 6 }]);
});
