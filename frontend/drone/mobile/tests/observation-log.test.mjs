import { test } from "node:test";
import assert from "node:assert/strict";
import {
  makeObservation, loadObservations, saveObservation, deleteObservation, NOTE_LIMIT,
} from "../src/observation-log.mjs";

function secureStore(values = new Map()) {
  return {
    values,
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
    async getItemAsync(key) { return values.get(key) ?? null; },
    async setItemAsync(key, raw, options) {
      assert.equal(options.keychainAccessible, this.WHEN_UNLOCKED_THIS_DEVICE_ONLY);
      values.set(key, raw);
    },
    async deleteItemAsync(key) { values.delete(key); },
  };
}

const bench = time => makeObservation("Bench housing inspected", "operator-bench", time);

test("operator explicitly chooses the context and records a valid device timestamp", () => {
  assert.deepEqual(makeObservation("  Replay paused  ", "simulation-review", 100), {
    text: "Replay paused", source: "simulation-review", recordedAt: 100,
  });
  for (const source of ["", "gps", "telemetry", "__proto__", ["operator-bench"]]) {
    assert.throws(() => makeObservation("Good", source, 100), /what you observed/);
  }
  for (const text of [null, "  a ", "x".repeat(251)]) {
    assert.throws(() => makeObservation(text, "operator-bench", 100), /3–250/);
  }
  for (const at of [NaN, -1, 1.1, 9e15, "100"]) {
    assert.throws(() => bench(at), /date and time/);
  }
});

test("saved bench and replay notes survive reopening, retaining origin and date", async () => {
  const store = secureStore();
  const later = bench(Date.UTC(2026, 10, 11, 6));
  const earlier = makeObservation("Recorded replay", "simulation-review", Date.UTC(2026, 10, 10, 6));
  await saveObservation(store, later);
  await saveObservation(store, earlier);
  const reopened = await loadObservations(secureStore(store.values));
  assert.deepEqual(reopened, [{slot:0, ...later}, {slot:1, ...earlier}]);
});

test("concurrent writes preserve the ten entries and an explicit deletion frees a slot", async () => {
  const store = secureStore();
  await Promise.all(Array.from({length:NOTE_LIMIT}, (_, n) => saveObservation(store, bench(n))));
  const full = await loadObservations(store);
  await assert.rejects(saveObservation(store, bench(99)), /10 saved note slots/);
  assert.deepEqual(await loadObservations(store), full);
  const deleted = full[3];
  await deleteObservation(store, deleted);
  await saveObservation(store, bench(99));
  await assert.rejects(deleteObservation(store, deleted), /has changed/);
  assert.equal((await loadObservations(store))[0].recordedAt, 99);
});

test("corrupt records remain visible and occupy their slots until manually removed", async () => {
  const store = secureStore();
  await saveObservation(store, bench(100));
  const [firstKey] = store.values.keys();
  store.values.set(firstKey, '{"text":');
  const second = await saveObservation(store, bench(101));
  assert.deepEqual(second, [{slot:1, ...bench(101)}, {slot:0, unreadable:true}]);
  assert.deepEqual(await deleteObservation(store, second[1]), [second[0]]);
});

test("storage failures preserve the log and a later retry can succeed", async () => {
  const store = secureStore();
  const [entry] = await saveObservation(store, bench(100));
  const {getItemAsync, deleteItemAsync, setItemAsync} = store;
  store.getItemAsync = async () => { throw new Error("locked"); };
  await assert.rejects(loadObservations(store), /locked/);
  await assert.rejects(saveObservation(store, bench(101)), /locked/);
  store.getItemAsync = getItemAsync;
  store.deleteItemAsync = async () => { throw new Error("delete failed"); };
  await assert.rejects(deleteObservation(store, entry), /delete failed/);
  store.deleteItemAsync = deleteItemAsync;
  store.setItemAsync = async () => { throw new Error("save failed"); };
  await assert.rejects(saveObservation(store, bench(101)), /save failed/);
  assert.deepEqual(await loadObservations(store), [entry]);
  store.setItemAsync = setItemAsync;
  assert.equal((await saveObservation(store, bench(101))).length, 2);
});
