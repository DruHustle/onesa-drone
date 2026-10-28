// Synthetic owner-run acceptance; fixture credentials enter stdin and never output.
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { randomUUID } from "node:crypto";
import {
  installAutomationSession,
  assertFixtureOrigin,
} from "./probe_policy.mjs";
const require = createRequire(
  new URL("../../frontend/package.json", import.meta.url),
);
const { chromium, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
  if (Buffer.concat(chunks).length > 16384)
    throw Error("Fixture size exceeded");
}
const fixture = JSON.parse(Buffer.concat(chunks));
if (
  ![
    "https://drone-staging.onesa.eu",
    "https://drone.onesa.eu",
    "http://127.0.0.1:3470",
  ].includes(fixture.origin)
)
  throw Error("Foreign probe origin refused");
if (!fixture.email || !fixture.password || fixture.password.length < 14)
  throw Error("Owned fixture identity required");
const executablePath =
  process.platform === "linux"
    ? existsSync("/usr/bin/chromium-browser")
      ? "/usr/bin/chromium-browser"
      : "/usr/bin/chromium"
    : undefined;
const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: executablePath
    ? [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--use-gl=angle",
        "--use-angle=gl-egl",
        "--disable-gpu-sandbox",
        "--ignore-gpu-blocklist",
      ]
    : [],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 950 },
  reducedMotion: "reduce",
});
await installAutomationSession(
  context,
  fixture.origin,
  fixture.protection_bypass,
);
const errors = [];
const checks = {};
const page = await context.newPage();
page.on("pageerror", (error) => errors.push(error.message));
try {
  const initial = await page.goto(fixture.origin);
  assertFixtureOrigin(page.url(), fixture.origin);
  if (initial?.status() !== 200)
    throw Error("Canonical frontend unavailable or protected session missing");
  await page.getByLabel("Email", { exact: true }).fill(fixture.email);
  assertFixtureOrigin(page.url(), fixture.origin);
  await page.getByLabel("Password", { exact: true }).fill(fixture.password);
  await page.getByRole("button", { name: "Sign in", exact: false }).click();
  await expect(
    page.getByRole("heading", { name: "Mission overview", exact: true }),
  ).toBeVisible({ timeout: 25000 });
  await expect(page.getByText("receiving", { exact: true })).toBeVisible({
    timeout: 25000,
  });
  await expect(page.locator(".scene canvas")).toBeVisible({ timeout: 25000 });
  await expect(page.locator(".scene-fallback")).toHaveCount(0);
  checks.authentication = checks.live_telemetry = checks.webgl = true;
  if (fixture.workflow) {
    const label = "Hosted qualification " + randomUUID().slice(0, 8);
    await page.getByRole("button", { name: "+ New delivery" }).click();
    await page.getByLabel("Delivery reference").fill(label);
    await page.getByRole("button", { name: "Register delivery" }).click();
    const track = await page.getByLabel("Private tracking link").inputValue();
    if (new URL(track).origin !== fixture.origin)
      throw Error("Tracking origin differs");
    await page.getByRole("button", { name: "Continue to mission" }).click();
    for (const action of [
      "Plan & assign",
      "Validate preflight",
      "Authorize simulation",
      "Launch simulation",
    ])
      await page.getByRole("button", { name: action, exact: true }).click();
    await expect(page.locator(".mission-detail .badge")).toHaveText(
      /completed/,
      { timeout: 120000 },
    );
    await page.getByRole("button", { name: "Play recorded telemetry" }).click();
    await expect(
      page.getByRole("heading", { name: "Historical replay" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Pause replay" }).click();
    const recipient = await context.newPage();
    await recipient.goto(track);
    assertFixtureOrigin(recipient.url(), fixture.origin);
    await expect(
      recipient.getByText("Simulated delivery confirmed.", { exact: true }),
    ).toBeVisible();
    await expect(recipient.locator("body")).not.toContainText(label);
    await recipient.close();
    checks.complete_delivery =
      checks.recorded_replay =
      checks.private_tracking =
        true;
  }
  const views = [];
  for (const colorScheme of ["light", "dark"])
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 950 });
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      if (width < 850)
        await page.getByRole("button", { name: "Toggle navigation" }).click();
      await page
        .getByRole("button", { name: "Dashboard", exact: true })
        .click();
      await expect(page.locator(".scene canvas")).toBeVisible();
      if (
        !(await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ))
      )
        throw Error("Horizontal overflow");
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      if (axe.violations.length)
        throw Error(
          "Accessibility check failed: " +
            axe.violations.map((v) => v.id).join(","),
        );
      views.push({ width, colorScheme, axe_violations: 0, webgl: true });
    }
  if (errors.length) throw Error("Browser runtime errors observed");
  checks.responsive_accessibility = true;
  console.log(
    JSON.stringify({
      state: "OBSERVED",
      mode: "simulation",
      checks,
      views,
      live_ai_invoked: false,
      physical_interfaces_used: false,
    }),
  );
} finally {
  await context.close();
  await browser.close();
}
