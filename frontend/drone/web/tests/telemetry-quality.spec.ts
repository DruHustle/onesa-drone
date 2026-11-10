import { test, expect } from "@playwright/test";

for (const width of [390, 768, 1440]) {
  test(`unavailable battery stays visibly unknown at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 950 });
    await page.addInitScript(() => {
      class SyntheticStream extends EventTarget {
        onerror = null;
        close() {}
      }
      Object.defineProperty(window, "EventSource", { value: SyntheticStream });
    });
    const sample = {
      seq: 5,
      mode: "simulation",
      simulation_seconds: 25,
      position: { lat: 52.52, lon: 13.405 },
      altitude_m: 60,
      ground_speed_mps: 0,
      heading: 20,
      battery_percent: 92,
      remaining_endurance_min: 30,
      flight_mode: "paused",
      motor_health: "illustrative-nominal",
      connectivity: "simulated",
      payload_state: "aboard",
      progress_percent: 20,
      battery_quality: "unavailable",
    };
    const mission = {
      id: "held",
      label: "Synthetic battery observation check",
      aircraft_id: "synthetic-aircraft",
      package_weight: 1,
      package_kind: "standard",
      state: "paused",
      scenario: "nominal",
      tick: 5,
      revision: 10,
      created_at: 1,
      scheduled_at: null,
      authorized_until: null,
      delivered: false,
      outcome: "aborted",
      origin: sample.position,
      destination: { lat: 52.523, lon: 13.411 },
      plan: {},
      last_telemetry: sample,
    };
    const aircraft = {
      id: "synthetic-aircraft",
      name: "Synthetic observation check",
      model: "Reference quad",
      manufacturer: "Illustrative",
      category: "multirotor",
      status: "in_mission",
      battery: null,
      battery_quality: "unavailable",
      capacity: 4,
      endurance: 35,
      firmware: "simulation",
      connectivity: "simulated",
      active_mission_id: mission.id,
      revision: 3,
      maintenance: [],
    };
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/v1/auth/me") {
        await route.fulfill({
          json: {
            id: "synthetic-user",
            email: "quality@example.test",
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
            aircraft: [aircraft],
            missions: [mission],
            counts: { paused: 1 },
            mode: "simulation",
            at: 1,
            truncated: { aircraft: false, missions: false },
          },
        });
      } else if (path === "/api/v1/missions/held/history") {
        await route.fulfill({
          json: {
            events: [
              {
                id: "held-event",
                at: 1,
                state: "paused",
                correlation_id: "synthetic",
                detail: {
                  reason:
                    "Invalid battery observation: simulation held for operator recovery",
                },
              },
            ],
            telemetry: [
              { ...sample, seq: 4, battery_quality: undefined },
              sample,
            ],
            retention_samples: 600,
          },
        });
      } else {
        throw new Error("Unexpected synthetic API route: " + path);
      }
    });
    await page.goto("/");
    const fleetBattery = page
      .locator(".metrics > *")
      .filter({ has: page.getByText("Fleet battery", { exact: true }) });
    await expect(fleetBattery).toContainText("Unavailable");
    const fleetRow = page
      .locator(".fleet-row")
      .filter({ hasText: aircraft.name });
    await expect(fleetRow).toContainText("Unavailable");
    await expect(fleetRow.getByRole("meter")).toHaveCount(0);
    await expect(page.locator(".scene canvas")).toBeVisible();
    await expect(
      page.getByText("3/3 NVIDIA models loaded", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`fleet-battery-unavailable-${width}.png`),
      fullPage: true,
    });
    if (width < 850)
      await page.getByRole("button", { name: "Toggle navigation" }).click();
    await page.getByRole("button", { name: "Aircraft", exact: true }).click();
    await expect(page.locator(".specs")).toContainText("Unavailable");
    if (width < 850)
      await page.getByRole("button", { name: "Toggle navigation" }).click();
    await page
      .getByRole("button", { name: "Mission control", exact: true })
      .click();
    const battery = page
      .locator(".metrics > *")
      .filter({ has: page.getByText("Battery", { exact: true }) });
    await expect(battery).toContainText("Unavailable");
    await expect(battery).toContainText("Simulation paused; check observation");
    await expect(battery).not.toContainText("92.0%");
    const chart = page.getByRole("img", {
      name: /Battery history:.*last battery unavailable/,
    });
    await expect(chart).toBeVisible();
    await expect(chart.locator("path").last()).toHaveAttribute("d", /^M0,/);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await expect(page.locator(".scene canvas")).toBeVisible();
    await expect(
      page.getByText("3/3 NVIDIA models loaded", { exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`battery-unavailable-${width}.png`),
      fullPage: true,
    });
  });
}
