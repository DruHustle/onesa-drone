export const featureViews = {
  fleet: "Aircraft",
  route: "Route planning",
  simulation: "3D simulator",
  telemetry: "Live telemetry",
} as const;

const requestedViewKey = "onesa.drone.requested-view";

export function rememberRequestedView(view: string) {
  try {
    sessionStorage.setItem(requestedViewKey, view);
  } catch {
    // The console remains reachable when browser storage is unavailable.
  }
}

export function clearRequestedView() {
  try {
    sessionStorage.removeItem(requestedViewKey);
  } catch {
    // Browser storage may be unavailable.
  }
}

function storedView() {
  try {
    return sessionStorage.getItem(requestedViewKey);
  } catch {
    return null;
  }
}

export function requestedView(): string {
  const slug = new URLSearchParams(location.search).get("view");
  const selected = Object.entries(featureViews).find(([id]) => id === slug)?.[1];
  if (selected) return selected;
  if (location.pathname === "/console") return "Dashboard";
  const previous = storedView();
  return Object.values(featureViews).find(view => view === previous) ?? "Dashboard";
}

export function showProductOverview() {
  if (location.pathname === "/explore") return true;
  const hosted = ["drone.onesa.eu", "drone-staging.onesa.eu"].includes(location.hostname);
  const params = new URLSearchParams(location.search);
  return hosted && location.pathname === "/" && !storedView() &&
    !params.has("registration") && !params.has("account_error");
}
