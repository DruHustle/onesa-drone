import { inOrder } from "./secure-operations.mjs";

export const NOTE_LIMIT = 10;
export const NOTE_SOURCES = Object.freeze({
  "operator-bench": "Bench observation",
  "simulation-review": "Simulation review",
});

export function makeObservation(text, source, recordedAt) {
  if (typeof source !== "string" || !Object.hasOwn(NOTE_SOURCES, source)) throw new RangeError("Choose what you observed.");
  const clean = typeof text === "string" ? text.trim() : "";
  if (clean.length < 3 || clean.length > 250) throw new RangeError("Enter a note of 3–250 characters.");
  if (!Number.isSafeInteger(recordedAt) || recordedAt < 0 || recordedAt > 8.64e15) {
    throw new RangeError("Check the date and time on this device.");
  }
  return { text: clean, source, recordedAt };
}

// Each note fits in a single secure-store value. A reset between operations
// cannot separate the note from an index or evict a previously saved entry.
const slotKey = slot => "onesa.drone.observation.v1." + slot;

function newestFirst(entries) {
  return entries.sort((a, b) => (b.recordedAt ?? -1) - (a.recordedAt ?? -1));
}

async function readSlots(store) {
  const entries = [];
  for (let slot = 0; slot < NOTE_LIMIT; slot++) {
    const raw = await store.getItemAsync(slotKey(slot));
    if (raw === null) continue;
    try {
      const value = JSON.parse(raw);
      entries.push({ slot, ...makeObservation(value.text, value.source, value.recordedAt) });
    } catch {
      entries.push({ slot, unreadable: true });
    }
  }
  return newestFirst(entries);
}

export function loadObservations(store) {
  return inOrder(store, () => readSlots(store));
}

export async function saveObservation(store, note) {
  const value = makeObservation(note.text, note.source, note.recordedAt);
  return inOrder(store, async () => {
    const entries = await readSlots(store);
    if (entries.length >= NOTE_LIMIT) {
      throw new RangeError("All 10 saved note slots are in use. Delete a saved note to make room.");
    }
    const used = new Set(entries.map(entry => entry.slot));
    let slot = 0;
    while (used.has(slot)) slot++;
    await store.setItemAsync(slotKey(slot), JSON.stringify(value), {
      keychainAccessible: store.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
    return newestFirst([{ slot, ...value }, ...entries]);
  });
}

export function deleteObservation(store, expected) {
  return inOrder(store, async () => {
    const entries = await readSlots(store);
    const current = entries.find(entry => entry.slot === expected.slot);
    if (!current) return entries;
    if (current.recordedAt !== expected.recordedAt || current.text !== expected.text ||
        current.source !== expected.source || current.unreadable !== expected.unreadable) {
      throw new RangeError("This saved note has changed. Refresh the list and select it again.");
    }
    await store.deleteItemAsync(slotKey(current.slot));
    return entries.filter(entry => entry.slot !== current.slot);
  });
}
