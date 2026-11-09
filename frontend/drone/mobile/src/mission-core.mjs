// Offline mission planning only. No physical flight or vendor protocol commands.
export const PURPOSES = Object.freeze([
  { id: "facility-security", label: "Security rounds", detail: "Perimeter observation with a human security operator." },
  { id: "farm-inspection", label: "Farm inspection", detail: "Review crop, irrigation and livestock areas without disturbing animals." },
  { id: "conservancy", label: "Conservancy patrol", detail: "Wildlife observation; never pursue, identify or confront people." },
  { id: "medical-delivery", label: "Medical delivery", detail: "Route proposal only; no payload transport has been qualified." },
  { id: "commerce-delivery", label: "E-commerce delivery", detail: "Destination and handoff draft; no carrying or release hardware." },
]);
export const MAX_WAYPOINTS = 12;
export const A77 = Object.freeze({
  manufacturer: "CHUBORY",
  model: "A77 brushless",
  vendorApp: "CHUBORY FLY",
  gps: "unverified",
  video: "vendor-app-local-only",
  commandBridge: false,
  cloudLink: false,
  payloadCertified: false,
  flightEnabled: false,
});
export const DEMO_ROUTE = Object.freeze([
  { lat: -17.8235, lon: 31.0451 },
  { lat: -17.8232, lon: 31.0455 },
  { lat: -17.8237, lon: 31.0458 },
  { lat: -17.8235, lon: 31.0451 },
]);

export function coordinate(value, axis) {
  if (axis !== "lat" && axis !== "lon") throw new TypeError("Unknown coordinate axis");
  if ((typeof value === "string" && !/^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$/.test(value.trim())) ||
      value === "" || value === null || value === undefined ||
      (typeof value !== "number" && typeof value !== "string")) {
    throw new RangeError("Enter a " + (axis === "lat" ? "latitude" : "longitude"));
  }
  const number = Number(value);
  const limit = axis === "lat" ? 85 : 180; // matches existing Drone simulation API
  if (!Number.isFinite(number) || Math.abs(number) > limit) {
    throw new RangeError("Coordinate is outside the supported planning range");
  }
  return Number(number.toFixed(6));
}

export function waypoint(latitude, longitude) {
  return { lat: coordinate(latitude, "lat"), lon: coordinate(longitude, "lon") };
}

export function distanceMetres(a, b) {
  const lat1 = coordinate(a.lat, "lat") * Math.PI / 180;
  const lat2 = coordinate(b.lat, "lat") * Math.PI / 180;
  const dLat = lat2 - lat1;
  const dLon = (coordinate(b.lon, "lon") - coordinate(a.lon, "lon")) * Math.PI / 180;
  const sin = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(sin)));
}

export function inspectRoute(points) {
  if (!Array.isArray(points) || points.length < 2 || points.length > MAX_WAYPOINTS) {
    throw new RangeError("Routes require 2 to " + MAX_WAYPOINTS + " points");
  }
  const waypoints = points.map(p => waypoint(p.lat, p.lon));
  let distance = 0;
  for (let i = 1; i < waypoints.length; i++) {
    const metres = distanceMetres(waypoints[i - 1], waypoints[i]);
    if (metres < 0.5) throw new RangeError("Consecutive waypoints must be different");
    distance += metres;
  }
  return {
    waypoints, distance_m: Math.round(distance),
    planning_status: "human-review-required",
    physical_flight_approved: false,
    advisories: [
      "Map geometry is not an authoritative airspace or terrain check.",
      "Check obstacles, wildlife, privacy, weather, airspace and visual line of sight.",
      "CHUBORY A77 GPS, autonomous waypoint API, video bridge and payload capability are unverified.",
    ],
  };
}

export function makeDraft({ title, purpose, points, id, now }) {
  const cleanTitle = String(title || "").trim();
  if (cleanTitle.length < 3 || cleanTitle.length > 80) {
    throw new RangeError("Mission name must have 3 to 80 characters");
  }
  if (!PURPOSES.some(p => p.id === purpose)) throw new RangeError("Unknown mission type");
  if (typeof id !== "string" || !/^[a-zA-Z0-9_-]{8,64}$/.test(id)) {
    throw new RangeError("Invalid draft identifier");
  }
  const created_at = Number(now);
  if (!Number.isSafeInteger(created_at) || created_at < 0) {
    throw new RangeError("Invalid creation time");
  }
  const route = inspectRoute(points);
  return {
    id, title: cleanTitle, purpose, created_at,
    waypoints: route.waypoints, distance_m: route.distance_m,
    status: "draft", source: "manual-planning",
    execution_enabled: false,
  };
}

export function simulationPosition(points, fraction) {
  const route = inspectRoute(points);
  const progress = Math.max(0, Math.min(1, Number.isFinite(fraction) ? fraction : 0));
  const segments = route.waypoints.slice(1).map((p, i) =>
    distanceMetres(route.waypoints[i], p));
  const distance = segments.reduce((a, b) => a + b, 0);
  let remaining = progress * distance;
  for (let i = 0; i < segments.length; i++) {
    const len = segments[i];
    if (remaining <= len || i === segments.length - 1) {
      const ratio = Math.max(0, Math.min(1, remaining / len));
      const from = route.waypoints[i], to = route.waypoints[i + 1];
      return {
        lat: Number((from.lat + (to.lat - from.lat) * ratio).toFixed(6)),
        lon: Number((from.lon + (to.lon - from.lon) * ratio).toFixed(6)),
        source: "synthetic-replay", is_live: false, progress_percent: Math.round(progress * 100),
      };
    }
    remaining -= len;
  }
  throw new Error("Unreachable synthetic route state");
}

export function aircraftLocation() {
  // A77 has no authenticated/qualified GPS stream. Never map a phone or synthetic
  // coordinate as an aircraft observation.
  return { available: false, position: null, source: "unverified-hardware", last_seen: null };
}
export function physicalDispatchStatus() {
  return {
    allowed: false,
    reason: "Physical flight is disabled until the A77 control, GPS, safety supervisor and regulations are qualified.",
  };
}
