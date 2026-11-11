import { test, expect } from "@playwright/test";

test("silent simulation feed labels the last snapshot and recovers on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.clock.install();
  await page.addInitScript(() => {
    const streams: EventTarget[] = [];
    class SyntheticStream extends EventTarget {
      constructor() {
        super();
        streams.push(this);
      }
      close() {}
    }
    Object.defineProperty(window, "EventSource", { value: SyntheticStream });
    Object.assign(window, {
      streams,
      sendFrame(index: number, type: string, value: unknown) {
        streams[index].dispatchEvent(
          new MessageEvent(type, { data: JSON.stringify(value) }),
        );
      },
    });
  });
  const operations = {
    mode: "simulation",
    at: 1,
    aircraft: [],
    missions: [],
    counts: {},
    truncated: { aircraft: false, missions: false },
  };
  const aircraft = {
    id: "test",
    name: "Synthetic ground unit",
    model: "Reference",
    manufacturer: "Illustrative",
    category: "multirotor",
    status: "available",
    battery: 86,
    capacity: 2,
    endurance: 30,
    firmware: "simulation",
    connectivity: "simulated",
    active_mission_id: null,
    revision: 1,
    maintenance: [],
  };
  let releaseSnapshot!: () => void;
  const held = new Promise<void>((resolve) => {
    releaseSnapshot = resolve;
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") {
      return route.fulfill({
        json: {
          id: "test",
          email: "synthetic@example.test",
          role: "viewer",
          tenant_id: "test",
          csrf: "test",
        },
      });
    }
    if (path === "/api/v1/settings") {
      return route.fulfill({
        json: {
          currency: "EUR",
          units: "metric",
          language: "en",
          region: "test",
        },
      });
    }
    if (path === "/api/v1/operations") {
      await held;
      return route.fulfill({ json: operations });
    }
    throw new Error("Unexpected request " + path);
  });
  await page.goto("/");
  await page.waitForFunction(() => (window as any).streams.length === 1);
  const frame = { ...operations, at: 2, aircraft: [aircraft] };
  await page.evaluate(
    (value) => (window as any).sendFrame(0, "telemetry", value),
    frame,
  );
  await expect(page.locator(".connection")).toHaveText("receiving");
  await expect(page.locator(".fleet-row")).toHaveText(/Synthetic ground unit/);
  const response = page.waitForResponse("**/api/v1/operations");
  releaseSnapshot();
  await (await response).finished();
  await page.clock.fastForward(12_000);
  await expect(page.locator(".connection")).toHaveText("updates delayed");
  await expect(
    page.getByRole("status").filter({ hasText: "Showing the last snapshot" }),
  ).toBeVisible();
  await expect(page.locator(".fleet-row")).toHaveText(/Synthetic ground unit/);
  await page.clock.fastForward(1000);
  await page.waitForFunction(() => (window as any).streams.length === 2);
  await page.evaluate(() => (window as any).sendFrame(0, "expired", {}));
  await page.evaluate(
    (value) => (window as any).sendFrame(1, "telemetry", value),
    {
      ...frame,
      at: 3,
      aircraft: [{ ...aircraft, name: "Recovered ground unit" }],
    },
  );
  await expect(page.locator(".connection")).toHaveText("receiving");
  await expect(page.getByText(/Showing the last snapshot/)).toHaveCount(0);
  await expect(page.locator(".fleet-row")).toHaveText(/Recovered ground unit/);
});
