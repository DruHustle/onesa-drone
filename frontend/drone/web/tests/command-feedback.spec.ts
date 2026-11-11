import { expect, test } from "@playwright/test";

test("simulator command feedback survives lost acknowledgements without automatic replay", async ({
  page,
}) => {
  let revision = 1;
  let writes = 0;
  let release!: () => void;
  const waitForOperator = new Promise<void>((resolve) => {
    release = resolve;
  });
  const aircraft = () => ({
    id: "sim-aircraft",
    name: "Test quad",
    model: "Test",
    manufacturer: "Test",
    category: "multirotor",
    status: "available",
    battery: 90,
    capacity: 2,
    endurance: 30,
    firmware: "simulation",
    connectivity: "simulated",
    active_mission_id: null,
    revision,
    maintenance: [],
  });
  await page.addInitScript(() => {
    class QuietStream extends EventTarget {
      close() {}
    }
    Object.defineProperty(window, "EventSource", { value: QuietStream });
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me"))
      return route.fulfill({
        json: {
          id: "operator",
          tenant_id: "demo",
          email: "operator@example.test",
          role: "operator",
          csrf: "synthetic",
        },
      });
    if (path.endsWith("/settings"))
      return route.fulfill({
        json: {
          currency: "EUR",
          units: "metric",
          language: "en",
          region: "test",
        },
      });
    if (path.endsWith("/operations"))
      return route.fulfill({
        json: {
          aircraft: [aircraft()],
          missions: [],
          counts: {},
          mode: "simulation",
          at: Date.now() / 1000,
          truncated: { aircraft: false, missions: false },
        },
      });
    if (path.endsWith("/aircraft/sim-aircraft/commands")) {
      const payload = route.request().postDataJSON();
      expect(payload.action).toBe("inspect");
      expect(payload.revision).toBe(revision);
      expect(payload.expires_at).toBeGreaterThan(Date.now() / 1000);
      ++writes;
      if (writes === 1) {
        await waitForOperator;
        ++revision;
        return route.fulfill({ json: aircraft() });
      }
      if (writes === 2)
        return route.fulfill({
          status: 422,
          json: { detail: "Synthetic rejection" },
        });
      if (writes === 3)
        return route.fulfill({
          status: 408,
          json: { detail: "Simulation command expired before execution" },
        });
      if (writes === 4) return route.abort("connectionreset");
    }
    throw new Error("Unexpected request " + path);
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Aircraft", exact: true }).click();
  const inspect = page.getByRole("button", { name: "Inspect", exact: true });
  const status = page.locator(".command-feedback");
  await inspect.click();
  await expect(status).toContainText("Pending");
  await expect(inspect).toBeDisabled();
  release();
  await expect(status).toContainText("Acknowledged by simulator");
  await inspect.click();
  await expect(status).toContainText("Failed");
  await inspect.click();
  await expect(status).toContainText("Timed out");
  await inspect.click();
  await expect(status).toContainText("Acknowledgement unavailable");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Mission overview" }),
  ).toBeVisible();
  await expect(page.locator(".fleet-row")).toContainText("Test quad");
  expect(writes).toBe(4);
});
