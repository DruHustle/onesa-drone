// SecureStore is injected: the module can be tested without a device.
import { inspectRoute, PURPOSES } from "./mission-core.mjs";

const INDEX = "onesa.drone.draft-index.v1";
const PREFIX = "onesa.drone.draft.";
const MAX_DRAFTS = 12;
const safeId = id => typeof id === "string" && /^[a-zA-Z0-9_-]{8,64}$/.test(id);
function key(id) {
  if (!safeId(id)) throw new RangeError("Invalid draft id");
  return PREFIX + id;
}
async function indexOf(store) {
  const value = await store.getItemAsync(INDEX);
  if (!value) return [];
  let ids;
  try { ids = JSON.parse(value); } catch { return []; }
  return Array.isArray(ids) ? ids.filter(safeId).slice(0, MAX_DRAFTS) : [];
}
function validDraft(value) {
  if (!value || !safeId(value.id) || value.status !== "draft" ||
      value.execution_enabled !== false || typeof value.title !== "string" ||
      value.title.length < 3 || value.title.length > 80 ||
      !PURPOSES.some(p => p.id === value.purpose)) return false;
  try { inspectRoute(value.waypoints); return true; } catch { return false; }
}
export async function loadDrafts(store) {
  const ids = await indexOf(store);
  const drafts = [];
  for (const id of ids) {
    let value;
    try { value = JSON.parse(await store.getItemAsync(key(id))); } catch { continue; }
    if (validDraft(value) && value.id === id) drafts.push(value);
  }
  return drafts;
}
export async function saveDraft(store, draft) {
  if (!validDraft(draft)) throw new RangeError("Invalid draft");
  const raw = JSON.stringify(draft);
  if (raw.length > 1800) throw new RangeError("Draft is too large for secure storage");
  const previousIds = await indexOf(store);
  const ids = [draft.id, ...previousIds.filter(id => id !== draft.id)].slice(0, MAX_DRAFTS);
  const location = key(draft.id);
  const previous = await store.getItemAsync(location);
  await store.setItemAsync(location, raw);
  try {
    await store.setItemAsync(INDEX, JSON.stringify(ids));
  } catch (error) {
    if (previous === null) await store.deleteItemAsync(location);
    else await store.setItemAsync(location, previous);
    throw error;
  }
  return draftsCount(ids);
}
function draftsCount(ids) { return ids.length; }
export async function deleteDraft(store, id) {
  const location = key(id);
  const ids = (await indexOf(store)).filter(other => other !== id);
  await store.setItemAsync(INDEX, JSON.stringify(ids));
  await store.deleteItemAsync(location);
}
