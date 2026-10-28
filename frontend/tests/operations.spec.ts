import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const pages = [
  "Dashboard",
  "Aircraft",
  "Fleet health",
  "Maintenance",
  "Mission control",
  "Delivery management",
  "Route planning",
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
async function login(page: any) {
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("browser@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Synthetic-browser-password-42!");
  await page.getByRole("button", { name: "Sign in", exact: false }).click();
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
for (const colorScheme of ["light", "dark"] as const)
  for (const width of [390, 768, 1440]) {
    test(`${colorScheme} ${width}: navigation, accessibility and rendering`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 950 });
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      await login(page);
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
