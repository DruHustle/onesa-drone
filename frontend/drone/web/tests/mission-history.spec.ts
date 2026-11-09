import { test, expect } from "@playwright/test";

test("changing mission clears the prior replay while the new history is loading", async ({
  page,
}) => {
  await page.addInitScript(() => {
    class SyntheticStream extends EventTarget {
      onerror = null;
      close() {}
    }
    Object.defineProperty(window, "EventSource", { value: SyntheticStream });
  });
  const sample = {
    seq: 9,
    mode: "simulation",
    simulation_seconds: 45,
    position: { lat: 52.52, lon: 13.405 },
    altitude_m: 60,
    ground_speed_mps: 10,
    heading: 20,
    battery_percent: 92,
    remaining_endurance_min: 30,
    flight_mode: "outbound",
    motor_health: "illustrative-nominal",
    connectivity: "simulated",
    payload_state: "aboard",
    progress_percent: 20,
  };
  const missions = ["first", "second"].map((id) => ({
    id,
    label: `${id} synthetic mission`,
    aircraft_id: null,
    package_weight: 1,
    package_kind: "standard",
    state: "completed",
    scenario: "nominal",
    tick: 20,
    revision: 10,
    created_at: 1,
    scheduled_at: null,
    authorized_until: null,
    delivered: true,
    outcome: null,
    origin: sample.position,
    destination: { lat: 52.523, lon: 13.411 },
    plan: {},
    last_telemetry: {
      ...sample,
      seq: 20,
      flight_mode: "completed",
      altitude_m: 0,
    },
  }));
  let release!: () => void;
  let requested!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const captured = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") {
      await route.fulfill({
        json: {
          id: "synthetic-user",
          email: "history@example.test",
          role: "viewer",
          tenant_id: "synthetic-tenant",
          csrf: "synthetic-csrf",
        },
      });
    } else if (path === "/api/v1/settings") {
      await route.fulfill({
        json: {
          currency: "EUR",
          units: "metric",
          language: "en",
          region: "synthetic",
        },
      });
    } else if (path === "/api/v1/operations") {
      await route.fulfill({
        json: {
          aircraft: [],
          missions,
          counts: { completed: 2 },
          mode: "simulation",
          at: 1,
          truncated: { aircraft: false, missions: false },
        },
      });
    } else if (/\/missions\/(first|second)\/history$/.test(path)) {
      const second = path.includes("/second/");
      if (second) {
        requested();
        await held;
      }
      await route.fulfill({
        json: {
          events: [
            {
              id: second ? "second-event" : "first-event",
              at: 1,
              state: "completed",
              detail: {
                reason: second ? "SECOND_MISSION_EVENT" : "FIRST_MISSION_EVENT",
              },
              correlation_id: "synthetic-correlation",
            },
          ],
          telemetry: [sample, { ...sample, seq: 10 }],
          retention_samples: 600,
        },
      });
    } else {
      throw new Error("Unexpected synthetic API route: " + path);
    }
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Mission control", exact: true })
    .click();
  await expect(page.locator(".timeline")).toContainText("FIRST_MISSION_EVENT");
  await page
    .getByRole("button", { name: "Play recorded telemetry", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Historical replay", exact: true }),
  ).toBeVisible();
  await page
    .locator(".mission-row")
    .filter({ hasText: "second synthetic mission" })
    .click();
  await captured;
  await expect(page.locator(".mission-detail h2")).toHaveText(
    "second synthetic mission",
  );
  await expect(page.locator("body")).not.toContainText("FIRST_MISSION_EVENT");
  await expect(page.locator(".replay")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Historical replay", exact: true }),
  ).toHaveCount(0);
  const response = page.waitForResponse("**/api/v1/missions/second/history");
  release();
  await (await response).finished();
  await expect(page.locator(".timeline")).toContainText("SECOND_MISSION_EVENT");
  await expect(
    page.getByRole("heading", { name: "Simulation telemetry", exact: true }),
  ).toBeVisible();
  await expect(page.locator("body")).not.toContainText("FIRST_MISSION_EVENT");
});
