import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

const source = readFileSync(
  new URL("../../tests/fixtures/controller-preview.plan", import.meta.url),
);

async function login(
  page: Page,
  account: "preview" | "session",
  navigate = true,
) {
  if (navigate) await page.goto("/");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`browser-flight-${account}@example.test`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Synthetic-browser-password-42!");
  const response = page.waitForResponse("**/api/v1/auth/login");
  await page.getByRole("button", { name: /^Sign in/ }).click();
  expect((await response).status()).toBe(200);
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Flight plans", exact: true }).click();
}

async function upload(page: Page, buffer = source) {
  await page.getByLabel("QGroundControl .plan file").setInputFiles({
    name: "synthetic-controller.plan",
    mimeType: "application/json",
    buffer,
  });
}

test("real API previews a controller plan without mission changes, with accessible mobile views", async ({
  page,
}) => {
  await login(page, "preview");
  const before = await (await page.request.get("/api/v1/operations")).json();
  await upload(page);
  await page
    .getByRole("button", { name: "Preview flight plan", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Offline preview · PX4" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Imported route geometry/ }),
  ).toBeVisible();
  await expect(page.locator(".flight-plan-items > li")).toHaveCount(3);
  await expect(page.locator(".flight-plan-digest")).toContainText(
    createHash("sha256").update(source).digest("hex"),
  );
  await expect(page.locator(".flight-plan-result")).toContainText(
    "Return altitude: controller-defined",
  );
  expect(
    (await (await page.request.get("/api/v1/operations")).json()).counts,
  ).toEqual(before.counts);
  for (const scheme of ["light", "dark"] as const) {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
  }
  const bad = JSON.parse(source.toString());
  bad.mission.items[1].command = 183;
  await upload(page, Buffer.from(JSON.stringify(bad)));
  await expect(page.locator(".flight-plan-result")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Preview flight plan", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Unsupported command");
  await upload(page, Buffer.alloc(12 * 1024 + 1, 120));
  await expect(page.getByRole("alert")).toContainText("at most 12 KiB");
  await expect(
    page.getByRole("button", { name: "Preview flight plan", exact: true }),
  ).toBeDisabled();
  await upload(page, Buffer.from([255, 254, 253]));
  await expect(page.getByRole("alert")).toContainText("could not be read");
});

test("a late preview is discarded after sign-out and the next session starts with no file", async ({
  page,
}) => {
  await login(page, "session");
  let release!: () => void;
  let received!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const captured = new Promise<void>((resolve) => {
    received = resolve;
  });
  await page.route("**/api/v1/flight-plans/preview", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    received();
    await held;
    await route.fulfill({
      json: { ...body, firmware: "PREVIOUS_SESSION_PRIVATE_PREVIEW" },
    });
  });
  await upload(page);
  await page
    .getByRole("button", { name: "Preview flight plan", exact: true })
    .click();
  await captured;
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await login(page, "session", false);
  const delivered = page.waitForResponse("**/api/v1/flight-plans/preview");
  release();
  await (await delivered).finished();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
  );
  await expect(
    page.getByRole("button", { name: "Preview flight plan", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("QGroundControl .plan file")).toHaveValue("");
  await expect(page.locator(".flight-plan-result")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText(
    "PREVIOUS_SESSION_PRIVATE_PREVIEW",
  );
});
