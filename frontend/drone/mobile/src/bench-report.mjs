// A bench record contains only observations entered by the person at the aircraft.
export const BENCH_CHECKS = [
  { id: "connected", label: "CHUBORY FLY indicates a connection to this aircraft" },
  { id: "disconnected", label: "CHUBORY FLY shows the loss of the local connection" },
  { id: "reconnected", label: "CHUBORY FLY shows the connection restored" },
  { id: "positionUnavailable", label: "Onesa Monitor shows actual aircraft position as unavailable" },
];

const STORAGE_KEY = "onesa.drone.bench-report.v1";
const OUTCOMES = new Set(["observed", "issue"]);
const SOURCE = "operator-entered-ground-bench";

function label(value, required = false) {
  if (typeof value !== "string" || value.length > 40 || /[\u0000-\u001f\u007f\u2028\u2029]/u.test(value)) {
    throw new RangeError("Use a single line of up to 40 characters per field.");
  }
  if (required && !value.trim()) throw new RangeError("Enter the aircraft asset label.");
  return value.trim();
}

function validTime(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) &&
    new Date(value).toISOString() === value;
}

function validate(report) {
  if (!report || report.version !== 1 || report.source !== SOURCE || !validTime(report.startedAt) ||
      !["ios", "android"].includes(report.platform) || !Array.isArray(report.results) ||
      report.results.length !== BENCH_CHECKS.length) throw new Error("Unrecognized bench record.");
  label(report.aircraft, true);
  label(report.firmware);
  label(report.vendorVersion);
  for (const [index, result] of report.results.entries()) {
    if (result?.id !== BENCH_CHECKS[index].id) throw new Error("Unrecognized bench check.");
    if (result.outcome === "untested" && result.at === null) continue;
    if (!OUTCOMES.has(result.outcome) || !validTime(result.at)) throw new Error("Invalid bench result.");
  }
  return report;
}

export function startReport({ aircraft, firmware, vendorVersion, platform }, now = new Date()) {
  return validate({
    version: 1, source: SOURCE, aircraft: label(aircraft, true), firmware: label(firmware),
    vendorVersion: label(vendorVersion), platform, startedAt: now.toISOString(),
    results: BENCH_CHECKS.map(({ id }) => ({ id, outcome: "untested", at: null })),
  });
}

export function markCheck(report, id, outcome, now = new Date()) {
  validate(report);
  if (!BENCH_CHECKS.some(check => check.id === id)) throw new Error("Unknown bench check.");
  const at = outcome === "untested" ? null : now.toISOString();
  return validate({ ...report, results: report.results.map(row => row.id === id ? { id, outcome, at } : row) });
}

export class UnreadableBenchRecord extends Error {}

export async function loadReport(store) {
  const raw = await store.getItemAsync(STORAGE_KEY);
  if (raw === null) return null;
  try {
    return validate(JSON.parse(raw));
  } catch {
    throw new UnreadableBenchRecord("The saved bench record has an unrecognized format.");
  }
}

export async function saveReport(store, report) {
  validate(report);
  await store.setItemAsync(STORAGE_KEY, JSON.stringify(report), {
    keychainAccessible: store.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function deleteReport(store) {
  await store.deleteItemAsync(STORAGE_KEY);
}

export const OUTCOME_LABELS = { untested: "Untested", observed: "Observed", issue: "Issue" };

export function formatReport(report) {
  validate(report);
  return [
    "Onesa Drone · CHUBORY A77 ground bench record",
    "Source: human observation. Timestamps use the phone clock. Flight readiness has not been assessed.",
    "Aircraft asset: " + report.aircraft,
    "Aircraft firmware: " + (report.firmware || "Unknown"),
    "CHUBORY FLY version: " + (report.vendorVersion || "Unknown"),
    "Phone platform: " + report.platform,
    "Started: " + report.startedAt,
    ...report.results.map((row, index) =>
      BENCH_CHECKS[index].label + " — " + OUTCOME_LABELS[row.outcome] + (row.at ? " · " + row.at : "")),
  ].join("\n");
}
