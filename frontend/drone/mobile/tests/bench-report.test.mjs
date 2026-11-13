import { test } from "node:test";
import assert from "node:assert/strict";
import { UnreadableBenchRecord, deleteReport, formatReport, loadReport, markCheck, saveReport, startReport } from "../src/bench-report.mjs";

const start = new Date("2026-11-11T14:00:00Z");
const later = new Date("2026-11-11T14:08:00Z");
const asset = { aircraft: "A77 bench unit 2", firmware: "", vendorVersion: "1.0", platform: "android" };
function memory() {
  let stored = null;
  return {
    getItemAsync: async () => stored,
    setItemAsync: async (_key, data) => { stored = data; },
    deleteItemAsync: async () => { stored = null; },
  };
}
test("handset records identity, unknowns and independent bench observations through a restart", async () => {
  const store = memory();
  assert.equal(await loadReport(store), null);
  const report = startReport(asset, start);
  const connected = markCheck(report, "connected", "observed", later);
  const updated = markCheck(connected, "disconnected", "issue", later);
  await saveReport(store, updated);
  const recovered = await loadReport(store);
  assert.deepEqual(recovered, updated);
  const message = formatReport(recovered);
  assert.match(message, /Source: human observation/);
  assert.match(message, /Aircraft firmware: Unknown/);
  assert.match(message, /restored — Untested/);
  assert.match(message, /connection — Issue · 2026-11-11T14:08:00.000Z/);
  assert.deepEqual(report.results.map(r => r.outcome), Array(4).fill("untested"));
  assert.equal(markCheck(updated, "connected", "untested").results[0].at, null);
  await deleteReport(store);
  assert.equal(await loadReport(store), null);
});
test("rejects unknown provenance, invalid input and malformed stored findings", async () => {
  assert.throws(() => startReport({ ...asset, aircraft: " " }));
  assert.throws(() => startReport({ ...asset, firmware: "2\n3" }));
  const report = startReport(asset);
  assert.throws(() => markCheck(report, "connected", "flight-ready"));
  assert.throws(() => markCheck(report, "other", "observed"));
  for (const raw of ["", "null", JSON.stringify({ ...report, source: "telemetry" }),
    JSON.stringify({ ...report, results: report.results.toReversed() }),
    JSON.stringify({ ...report, results: report.results.map(r => ({ ...r, outcome: "observed" })) })]) {
    const store = memory();
    await store.setItemAsync("", raw);
    await assert.rejects(loadReport(store), UnreadableBenchRecord);
    assert.equal(await store.getItemAsync(), raw);
  }
});
test("a storage failure preserves the saved findings and rejects the attempted change", async () => {
  const store = memory();
  const previous = startReport(asset);
  await saveReport(store, previous);
  store.setItemAsync = async () => { throw new Error("Device locked"); };
  await assert.rejects(saveReport(store, markCheck(previous, "connected", "observed")), /Device locked/);
  assert.deepEqual(await loadReport(store), previous);
});
