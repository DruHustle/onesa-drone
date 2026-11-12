import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const pages = [
  "Dashboard",
  "Aircraft",
  "Fleet health",
  "Maintenance",
  "Mission control",
  "Delivery management",
  "Route planning",
  "Flight plans",
  "Live telemetry",
  "3D simulator",
  "Digital twins",
  "Scenarios",
  "AI assistant",
  "Analytics",
  "Cybersecurity",
  "Infrastructure monitor",
  "Administration",
];
async function login(page: Page, account = "delivery") {
  await page.goto("/");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`browser-${account}@example.test`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Synthetic-browser-password-42!");
  const response = page.waitForResponse("**/api/v1/auth/login");
  await page.getByRole("button", { name: "Sign in", exact: false }).click();
  expect((await response).status()).toBe(200);
  await expect(
    page.getByRole("heading", { name: "Mission overview", exact: true }),
  ).toBeVisible();
}
test("real delivery, telemetry, replay, assistant and tracking", async ({
  page,
  context,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.getByRole("button", { name: "+ Register aircraft" }).click();
  await page.getByRole("button", { name: "Save aircraft" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "+ New delivery" }).click();
  await page.getByLabel("Delivery reference").fill("Browser acceptance parcel");
  await page.getByRole("button", { name: "Register delivery" }).click();
  const link = await page.getByLabel("Private tracking link").inputValue();
  await page.getByRole("button", { name: "Continue to mission" }).click();
  await page
    .getByRole("button", { name: "Route planning", exact: true })
    .click();
  await page.getByRole("button", { name: "Build dispatch preview" }).click();
  await expect(page.locator(".dispatch-order li")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Plan this delivery" }),
  ).toBeEnabled();
  await page.setViewportSize({ width: 390, height: 950 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  const planningAxe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(planningAxe.violations.map((violation) => violation.id)).toEqual([]);
  await page.screenshot({
    path: "../artifacts/planning-preview-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByLabel("Route preference").selectOption("1");
  for (const action of [
    "Plan & assign",
    "Validate preflight",
    "Authorize simulation",
    "Launch simulation",
  ])
    await page.getByRole("button", { name: action, exact: true }).click();
  await expect(page.locator(".route-options")).toContainText(
    "Alternative 1 · Selected",
  );
  await expect(page.getByText("receiving", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Simulation telemetry", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".scene canvas")).toBeVisible();
  await expect(page.locator(".scene-fallback")).toHaveCount(0);
  await page.waitForTimeout(2500);
  await testInfo.attach("active-scene-performance", {
    body: JSON.stringify(
      await page.evaluate(() => ({
        caption: document.querySelector(".scene-caption")?.textContent,
        heap: (performance as any).memory?.usedJSHeapSize,
      })),
    ),
    contentType: "application/json",
  });
  await expect(page.locator(".mission-detail .badge")).toHaveText(/completed/, {
    timeout: 65000,
  });
  await page.getByRole("button", { name: "Play recorded telemetry" }).click();
  await expect(
    page.getByRole("heading", { name: "Historical replay" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause replay" }).click();
  const track = await context.newPage();
  await track.goto(link);
  await expect(
    track.getByText("Simulated delivery confirmed.", { exact: true }),
  ).toBeVisible();
  await expect(track.locator("body")).not.toContainText(
    "Browser acceptance parcel",
  );
  await track.close();
  await page.getByRole("button", { name: "AI assistant", exact: true }).click();
  await page
    .getByLabel("Your question")
    .fill("Explain completed deliveries and battery reserve.");
  await page
    .getByRole("button", { name: "Ask assistant", exact: true })
    .click();
  await expect(page.locator(".assistant-answer")).toContainText(
    "deterministic-operational-summary",
  );
  expect(errors).toEqual([]);
});
test("fleet maintenance, delivery cancellation, incident resolution and report persist", async ({
  page,
}) => {
  await login(page, "fleet-review");
  const button = (name: string) =>
    page.getByRole("button", { name, exact: true });
  await button("+ Register aircraft").click();
  await page.getByLabel("Aircraft identifier").fill("SIM-REVIEW");
  await button("Save aircraft").click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await button("Maintenance").click();
  const aircraft = page.getByRole("article").filter({ hasText: "SIM-REVIEW" });
  await aircraft.getByRole("button", { name: "Edit", exact: true }).click();
  await page
    .getByLabel("Model", { exact: true })
    .fill("Reviewed reference model");
  await button("Save aircraft").click();
  await expect(aircraft).toContainText("Reviewed reference model");
  await aircraft.getByRole("button", { name: "Inspect", exact: true }).click();
  await expect(aircraft).toContainText("Illustrative software inspection");
  const charged = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/commands"),
  );
  await aircraft.getByRole("button", { name: "Recharge", exact: true }).click();
  expect((await (await charged).json()).battery).toBe(100);
  await aircraft
    .getByRole("button", { name: "Decommission", exact: true })
    .click();
  await expect(
    aircraft.getByRole("button", { name: "Recharge", exact: true }),
  ).toBeDisabled();
  await aircraft.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(
    aircraft.getByRole("button", { name: "Recharge", exact: true }),
  ).toBeEnabled();

  await button("+ New delivery").click();
  await page.getByLabel("Delivery reference").fill("Cancelled review parcel");
  await button("Register delivery").click();
  await button("Continue to mission").click();
  await button("Plan & assign").click();
  await button("Reschedule +5 min").click();
  await button("Cancel mission").click();
  await expect(page.locator(".mission-detail .badge")).toHaveText(/cancelled/);
  await button("Cybersecurity").click();
  await page
    .getByLabel("Title", { exact: true })
    .fill("Synthetic inspection alert");
  await page
    .getByLabel("Details", { exact: true })
    .fill("Fixture review of a simulated link loss.");
  await button("Record incident").click();
  const incident = page
    .getByRole("article")
    .filter({ hasText: "Synthetic inspection alert" });
  await incident.getByRole("button", { name: "Resolve" }).click();
  await expect(incident).toContainText("resolved");
  await page.reload();
  await button("Cybersecurity").click();
  await expect(incident).toContainText("resolved");
  await button("Analytics").click();
  const downloadEvent = page.waitForEvent("download");
  await button("Download report").click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("onesa-simulation-report.json");
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream!) chunks.push(chunk);
  const report = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  expect(report.mode).toBe("simulation");
  expect(
    report.missions.map((mission: { state: string }) => mission.state),
  ).toEqual(["cancelled"]);
  expect(JSON.stringify(report)).not.toContain("Cancelled review parcel");
});

for (const colorScheme of ["light", "dark"] as const)
  for (const width of [390, 768, 1440]) {
    test(`${colorScheme} ${width}: navigation, accessibility and rendering`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 950 });
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      await login(page, `navigation-${colorScheme}-${width}`);
      for (const name of pages) {
        if (width < 850)
          await page.getByRole("button", { name: "Toggle navigation" }).click();
        await page.getByRole("button", { name, exact: true }).click();
        await expect(
          page
            .getByRole("heading", {
              name: name === "Dashboard" ? "Mission overview" : name,
              exact: true,
            })
            .first(),
        ).toBeVisible();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBeTruthy();
      }
      if (width < 850)
        await page.getByRole("button", { name: "Toggle navigation" }).click();
      await page
        .getByRole("button", { name: "Dashboard", exact: true })
        .click();
      await page.waitForTimeout(2200);
      await expect(page.locator(".scene canvas")).toBeVisible();
      await expect(page.locator(".scene-fallback")).toHaveCount(0);
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      expect(
        axe.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          nodes: v.nodes.map((n) => n.target),
        })),
      ).toEqual([]);
      await page.screenshot({
        path: `../artifacts/console-${colorScheme}-${width}.png`,
        fullPage: true,
      });
      await testInfo.attach("scene-performance", {
        body: JSON.stringify(
          await page.evaluate(() => ({
            scene: document.querySelector(".scene-caption")?.textContent,
            heap: (performance as any).memory?.usedJSHeapSize,
            resources: performance
              .getEntriesByType("resource")
              .map((r: any) => ({
                name: new URL(r.name).pathname,
                bytes: r.transferSize,
                duration: r.duration,
              })),
          })),
        ),
        contentType: "application/json",
      });
    });
  }
