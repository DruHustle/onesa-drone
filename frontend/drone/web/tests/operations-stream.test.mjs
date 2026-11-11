import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { subscribeToOperations } from "../src/operationsStream.ts";

const nativeStream = globalThis.EventSource;
const nativeFetch = globalThis.fetch;
let streams, statuses, snapshots, expired, stop;
const frame = {
  mode: "simulation",
  at: 1,
  aircraft: [],
  missions: [],
  counts: {},
  truncated: { aircraft: false, missions: false },
};
function emit(stream, type, value) {
  stream.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(value) }));
}

beforeEach((t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  streams = [];
  statuses = [];
  snapshots = [];
  expired = 0;
  globalThis.EventSource = class extends EventTarget {
    closed = false;
    constructor(path) {
      super();
      assert.equal(path, "/api/v1/stream");
      streams.push(this);
    }
    close() {
      this.closed = true;
    }
  };
  stop = subscribeToOperations(
    (value) => snapshots.push(value),
    (status) => statuses.push(status),
    () => {
      expired++;
    },
  );
});
afterEach(() => {
  stop();
  globalThis.EventSource = nativeStream;
  globalThis.fetch = nativeFetch;
});

test("a silent feed becomes stale and reconnects, ignoring events from the closed stream", (t) => {
  const first = streams[0];
  emit(first, "telemetry", frame);
  t.mock.timers.tick(11_000);
  emit(first, "telemetry", { ...frame, at: 2 });
  t.mock.timers.tick(11_999);
  assert.equal(statuses.at(-1), "receiving");
  t.mock.timers.tick(1);
  assert.equal(statuses.at(-1), "updates delayed");
  assert.ok(first.closed);
  t.mock.timers.tick(1000);
  assert.equal(streams.length, 2);
  emit(first, "expired", {});
  emit(first, "telemetry", frame);
  assert.equal(expired, 0);
  assert.equal(snapshots.length, 2);
  emit(streams[1], "telemetry", { ...frame, at: 3 });
  assert.equal(statuses.at(-1), "receiving");
  assert.equal(snapshots.at(-1).at, 3);
});

test("identity and storage failures retain the session and back off when failures repeat", (t) => {
  emit(streams[0], "unavailable", { reason: "identity" });
  assert.equal(statuses.at(-1), "account service unavailable");
  streams[0].onerror();
  t.mock.timers.tick(1000);
  emit(streams[1], "unavailable", { reason: "storage" });
  assert.equal(statuses.at(-1), "storage unavailable");
  t.mock.timers.tick(1999);
  assert.equal(streams.length, 2);
  t.mock.timers.tick(1);
  assert.equal(streams.length, 3);
  emit(streams[2], "telemetry", {});
  assert.equal(statuses.at(-1), "updates unavailable");
  assert.equal(expired, 0);
  assert.deepEqual(snapshots, []);
  stop();
  t.mock.timers.tick(60_000);
  assert.equal(streams.length, 3);
});

for (const status of [401, 403, 503]) {
  test(`failed stream handshake rechecks session (HTTP ${status})`, async (t) => {
    globalThis.fetch = async (url, init) => {
      assert.equal(url, "/api/v1/auth/me");
      assert.equal(init.method, "GET");
      return Response.json({ detail: "synthetic reason" }, { status });
    };
    await streams[0].onerror();
    t.mock.timers.tick(60_000);
    assert.equal(expired, status === 503 ? 0 : 1);
    assert.equal(streams.length, status === 503 ? 2 : 1);
  });
}

test("cleanup invalidates an in-flight session check", async (t) => {
  let resolve;
  globalThis.fetch = () =>
    new Promise((done) => {
      resolve = done;
    });
  const error = streams[0].onerror();
  stop();
  resolve(Response.json({ detail: "late response" }, { status: 401 }));
  await error;
  assert.equal(expired, 0);
  t.mock.timers.tick(60_000);
  assert.equal(streams.length, 1);
});

test("repeating or older snapshots cannot keep stale telemetry healthy after reconnect", (t) => {
  emit(streams[0], "telemetry", { ...frame, at: 3 });
  t.mock.timers.tick(11_000);
  emit(streams[0], "telemetry", { ...frame, at: 3 });
  t.mock.timers.tick(1000);
  assert.equal(statuses.at(-1), "updates delayed");
  t.mock.timers.tick(1000);
  emit(streams[1], "telemetry", { ...frame, at: 2 });
  assert.equal(snapshots.length, 1);
  assert.equal(statuses.at(-1), "updates delayed");
  emit(streams[1], "telemetry", { ...frame, at: 4 });
  assert.equal(statuses.at(-1), "receiving");
  assert.equal(snapshots.at(-1).at, 4);
});
