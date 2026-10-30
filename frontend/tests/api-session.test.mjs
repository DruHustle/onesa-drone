import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { api, setCSRF } from "../src/api.ts";

const originalFetch = globalThis.fetch;
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
};
beforeEach(() => {
  setCSRF("synthetic-session-a");
  globalThis.fetch = async () => {
    throw new Error("Unexpected network request");
  };
});
afterEach(() => {
  globalThis.fetch = originalFetch;
  setCSRF("");
});

test(
  "a delayed response from a previous session cannot populate the next workspace",
  { timeout: 2000 },
  async () => {
    const response = deferred();
    let requests = 0;
    globalThis.fetch = () => {
      requests++;
      return response.promise;
    };
    let visible = { aircraft: ["current-session-aircraft"] };
    const oldRequest = api("/operations").then((value) => {
      visible = value;
    });
    setCSRF("synthetic-session-b");
    const rejected = assert.rejects(oldRequest, /Session changed/);
    response.resolve(
      new Response(
        JSON.stringify({ aircraft: ["previous-session-private-aircraft"] }),
      ),
    );
    await rejected;
    assert.deepEqual(visible, { aircraft: ["current-session-aircraft"] });
    assert.equal(requests, 1, "a session change never replays a request");
  },
);

test(
  "a session change while reading JSON also refuses the previous response",
  { timeout: 2000 },
  async () => {
    const body = deferred(),
      reading = deferred();
    globalThis.fetch = async () => ({
      ok: true,
      json: () => {
        reading.resolve();
        return body.promise;
      },
    });
    const oldRequest = api("/operations");
    await reading.promise;
    setCSRF("synthetic-session-b");
    const rejected = assert.rejects(oldRequest, /Session changed/);
    body.resolve({ aircraft: ["previous-session-private-aircraft"] });
    await rejected;
  },
);

test(
  "logout invalidates a pending response without replay or new commands",
  { timeout: 2000 },
  async () => {
    const response = deferred();
    const requests = [];
    globalThis.fetch = (url, options) => {
      requests.push({ url, options });
      return response.promise;
    };
    const oldRequest = api("/assistant", "POST", {
      question: "Synthetic advice",
    });
    setCSRF("");
    const rejected = assert.rejects(oldRequest, /Session changed/);
    response.resolve(
      new Response(JSON.stringify({ answer: "Previous session advice" })),
    );
    await rejected;
    assert.equal(requests.length, 1);
    assert.equal(
      requests[0].options.headers["X-CSRF-Token"],
      "synthetic-session-a",
    );
  },
);

test("new-session requests retain the current CSRF and return their own result", async () => {
  setCSRF("synthetic-session-b");
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/v1/missions");
    assert.equal(options.headers["X-CSRF-Token"], "synthetic-session-b");
    assert.equal(options.headers["Idempotency-Key"], "synthetic-idempotency");
    return new Response(JSON.stringify({ id: "current-session-mission" }));
  };
  assert.deepEqual(
    await api("/missions", "POST", {}, "synthetic-idempotency"),
    { id: "current-session-mission" },
  );
});

test("current-session HTTP failures remain failures", async () => {
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({ detail: "Mission changed; reload before retrying" }),
      { status: 409 },
    );
  await assert.rejects(
    api("/missions/synthetic/commands", "POST", {}),
    /Mission changed/,
  );
});
