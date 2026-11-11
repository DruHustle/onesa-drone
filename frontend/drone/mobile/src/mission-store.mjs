// SecureStore is injected: the module can be tested without a device.
import { inspectRoute, PURPOSES } from "./mission-core.mjs";

const INDEX = "onesa.drone.draft-index.v1";
const PREFIX = "onesa.drone.draft.";
const MAX_DRAFTS = 12;
const operations = new WeakMap();

function inOrder(store, operation) {
  const pending = operations.get(store) || Promise.resolve();
  const next = pending.then(operation);
  operations.set(store, next.catch(() => {}));
  return next;
}
const safeId = id => typeof id === "string" && /^[a-zA-Z0-9_-]{8,64}$/.test(id);
function key(id) {
  if (!safeId(id)) throw new RangeError("Invalid draft id");
  return PREFIX + id;
}
async function indexOf(store) {
  const value = await store.getItemAsync(INDEX);
  if (value === null) return [];
  let ids;
  try { ids = JSON.parse(value); } catch { /* Report invalid metadata below. */ }
  if (!Array.isArray(ids) || !ids.every(safeId)) {
    throw new Error("The saved draft list cannot be read. Your encrypted drafts have been preserved.");
  }
  return [...new Set(ids)];
}
function validDraft(value) {
  if (!value || !safeId(value.id) || value.status !== "draft" ||
      value.execution_enabled !== false || typeof value.title !== "string" ||
      value.title.length < 3 || value.title.length > 80 ||
      !PURPOSES.some(p => p.id === value.purpose)) return false;
  try { inspectRoute(value.waypoints); return true; } catch { return false; }
}
export async function loadDrafts(store) {
  return inOrder(store, () => readDrafts(store));
}
async function readDrafts(store) {
  const ids = await indexOf(store);
  const drafts = [];
  for (const id of ids) {
    const raw = await store.getItemAsync(key(id));
    let value;
    try { value = JSON.parse(raw); } catch { continue; }
    if (validDraft(value) && value.id === id) drafts.push(value);
  }
  return drafts;
}
export async function saveDraft(store, draft) {
  if (!validDraft(draft)) throw new RangeError("Invalid draft");
  const raw = JSON.stringify(draft);
  if (raw.length > 1800) throw new RangeError("Draft is too large for secure storage");
  return inOrder(store, async () => {
    const location = key(draft.id);
    const ids = await indexOf(store);
    // An interrupted save or deletion can leave an index entry without a payload.
    // Check existence before allocating a slot and keep every existing record.
    const retained = [];
    for (const id of ids) {
      if (id !== draft.id && await store.getItemAsync(key(id)) !== null) retained.push(id);
    }
    if (retained.length >= MAX_DRAFTS) {
      throw new RangeError("All 12 draft slots are in use. Delete a saved draft before adding another.");
    }
    // Reserve the index entry first. A restart can leave a recoverable empty slot,
    // while a written private record always has a discoverable key.
    await store.setItemAsync(INDEX, JSON.stringify([draft.id, ...retained]));
    await store.setItemAsync(location, raw);
    return retained.length + 1;
  });
}
export async function deleteDraft(store, id) {
  const location = key(id);
  return inOrder(store, async () => {
    const ids = await indexOf(store);
    await store.deleteItemAsync(location);
    await store.setItemAsync(INDEX, JSON.stringify(ids.filter(other => other !== id)));
  });
}
