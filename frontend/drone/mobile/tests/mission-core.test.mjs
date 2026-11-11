import { test } from "node:test";
import assert from "node:assert/strict";
import {
  A77, DEMO_ROUTE, PURPOSES, aircraftLocation, coordinate, waypoint,
  inspectRoute, makeDraft, simulationPosition, physicalDispatchStatus,
} from "../src/mission-core.mjs";
import { saveDraft, loadDrafts, deleteDraft } from "../src/mission-store.mjs";

test("A77 is not silently treated as a GPS or video-bridge aircraft", () => {
  assert.equal(A77.commandBridge, false);
  assert.equal(A77.flightEnabled, false);
  assert.equal(A77.gps, "unverified");
  assert.equal(aircraftLocation().position, null);
  assert.equal(physicalDispatchStatus().allowed, false);
});
test("mission purposes include wildlife, security, crop and medical use without launches", () => {
  assert.deepEqual(PURPOSES.map(p => p.id), [
    "facility-security", "farm-inspection", "conservancy",
    "medical-delivery", "commerce-delivery",
  ]);
});
test("coordinate input validates range, blanks and nonnumbers", () => {
  assert.deepEqual(waypoint("-17.1234567", "31.0000001"), { lat: -17.123457, lon: 31 });
  for (const [value, axis] of [["", "lat"], ["   ", "lon"], ["NaN", "lon"], ["Infinity", "lat"], [181, "lon"], [90, "lat"]]) {
    assert.throws(() => coordinate(value, axis), RangeError);
  }
});
test("route calculation refuses duplicate and malformed points", () => {
  const route = inspectRoute(DEMO_ROUTE);
  assert.ok(route.distance_m > 100);
  assert.equal(route.physical_flight_approved, false);
  assert.throws(() => inspectRoute([DEMO_ROUTE[0]]), RangeError);
  assert.throws(() => inspectRoute([DEMO_ROUTE[0], DEMO_ROUTE[0]]), RangeError);
  assert.throws(() => inspectRoute(Array.from({ length: 13 }, (_, i) =>
    ({ lat: -17.8 + i / 100, lon: 31 }))), RangeError);
});
test("synthetic replay is bounded and never labelled as live GPS", () => {
  const start = simulationPosition(DEMO_ROUTE, -2);
  const end = simulationPosition(DEMO_ROUTE, 2);
  assert.deepEqual({ lat: start.lat, lon: start.lon }, DEMO_ROUTE[0]);
  assert.deepEqual({ lat: end.lat, lon: end.lon }, DEMO_ROUTE.at(-1));
  for (const progress of [0, 0.2, 0.5, 0.99, 1]) {
    const sample = simulationPosition(DEMO_ROUTE, progress);
    assert.equal(sample.is_live, false);
    assert.equal(sample.source, "synthetic-replay");
  }
});
function fakeStore() {
  const values = new Map();
  return {
    values,
    async getItemAsync(key) { return values.get(key) ?? null; },
    async setItemAsync(key, value) { values.set(key, value); },
    async deleteItemAsync(key) { values.delete(key); },
  };
}
test("secure draft store preserves simulated routes and deletes them", async () => {
  const storage = fakeStore();
  const draft = makeDraft({
    id: "draft_abc12345", title: "Wildlife perimeter", purpose: "conservancy",
    points: DEMO_ROUTE, now: 1793900000000,
  });
  assert.equal(await saveDraft(storage, draft), 1);
  assert.deepEqual(await loadDrafts(storage), [draft]);
  await deleteDraft(storage, draft.id);
  assert.deepEqual(await loadDrafts(storage), []);
});
test("malformed stored records are not trusted", async () => {
  const storage = fakeStore();
  storage.values.set("onesa.drone.draft-index.v1", JSON.stringify(["draft_abc12345"]));
  storage.values.set("onesa.drone.draft.draft_abc12345",
    JSON.stringify({ id: "draft_abc12345", title: "Bad", purpose: "conservancy",
      status: "draft", execution_enabled: true, waypoints: DEMO_ROUTE }));
  assert.deepEqual(await loadDrafts(storage), []);
});
test("secure index-write failure leaves no private record", async () => {
  const storage = fakeStore();
  const draft = makeDraft({
    id: "draft_abc12345", title: "Crop inspection", purpose: "farm-inspection",
    points: DEMO_ROUTE, now: 1793900000000,
  });
  const set = storage.setItemAsync;
  storage.setItemAsync = async (key, value) => {
    if (key.endsWith("draft-index.v1")) throw new Error("Keychain unavailable");
    return set(key, value);
  };
  await assert.rejects(saveDraft(storage, draft), /Keychain unavailable/);
  assert.equal(storage.values.has("onesa.drone.draft." + draft.id), false);
});

function numberedDraft(n) {
  return makeDraft({
    id: "draft_example_" + n, title: "Inspection " + n, purpose: "farm-inspection",
    points: DEMO_ROUTE, now: 1793900000000 + n,
  });
}

test("concurrent saves preserve all 12 drafts and refuse overflow without data loss", async () => {
  const store = fakeStore();
  const drafts = Array.from({ length: 12 }, (_, n) => numberedDraft(n));
  await Promise.all(drafts.map(draft => saveDraft(store, draft)));
  await assert.rejects(saveDraft(store, numberedDraft(12)), /12 draft slots/);
  assert.deepEqual(await loadDrafts(store), drafts.toReversed());
  assert.equal(store.values.size, 13);
  const updated = { ...drafts[0], title: "Revised inspection" };
  await saveDraft(store, updated);
  assert.equal((await loadDrafts(store))[0].title, updated.title);
  await deleteDraft(store, drafts[1].id);
  assert.equal(await saveDraft(store, numberedDraft(12)), 12);
});

test("failed secure deletion keeps the record visible for a retry", async () => {
  const store = fakeStore();
  const draft = numberedDraft(1);
  await saveDraft(store, draft);
  const remove = store.deleteItemAsync;
  store.deleteItemAsync = async () => { throw new Error("Keychain locked"); };
  await assert.rejects(deleteDraft(store, draft.id), /Keychain locked/);
  assert.deepEqual(await loadDrafts(store), [draft]);
  store.deleteItemAsync = remove;
  await deleteDraft(store, draft.id);
  assert.deepEqual(await loadDrafts(store), []);
});

test("a failed payload write leaves room for the next save", async () => {
  const store = fakeStore();
  const write = store.setItemAsync;
  const abandoned = numberedDraft(0);
  store.setItemAsync = async (key, value) => {
    if (key.endsWith(abandoned.id)) throw new Error("Write interrupted");
    return write(key, value);
  };
  await assert.rejects(saveDraft(store, abandoned), /Write interrupted/);
  store.setItemAsync = write;
  for (let n = 1; n <= 12; n++) await saveDraft(store, numberedDraft(n));
  assert.equal((await loadDrafts(store)).length, 12);
  assert.equal(store.values.size, 13);
});
