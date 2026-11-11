import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { storeListing } from "../src/mobile-store-listing.ts";

const mobileListings = JSON.parse(readFileSync(new URL("../src/mobile-downloads.json", import.meta.url), "utf8"));

// UI acceptance uses synthetic local identity responses. Protocol and tenant
// authorization are covered separately against the real Python application.
const first = "11111111-1111-4111-8111-111111111111";
const second = "22222222-2222-4222-8222-222222222222";
const account = {
  id: "identity:33333333-3333-4333-8333-333333333333",
  email: "shared-admin@example.test",
  role: "admin",
  tenant_id: null as string | null,
  csrf: "synthetic-shared-csrf",
  identity_managed: true,
  global_admin: true,
  account_url: "http://127.0.0.1:8500/account",
  access_url: "http://127.0.0.1:8500/account?tab=access",
};
const operations = {
  aircraft: [],
  missions: [],
  counts: {},
  mode: "simulation",
  at: 0,
  truncated: { aircraft: false, missions: false },
};

async function identityUI(
  page: Page,
  options: {
    signedIn?: boolean;
    memberships?: boolean;
    partialLogout?: boolean;
  } = {},
) {
  let user = { ...account };
  let signedIn = options.signedIn;
  const writes: Array<{ path: string; body: unknown }> = [];
  await page.addInitScript((value) => {
    class SyntheticStream extends EventTarget {
      onerror = null;
      closed = false;
      constructor() {
        super();
        queueMicrotask(() => {
          if (!this.closed)
            this.dispatchEvent(
              new MessageEvent("telemetry", { data: JSON.stringify(value) }),
            );
        });
      }
      close() {
        this.closed = true;
      }
    }
    Object.defineProperty(window, "EventSource", { value: SyntheticStream });
  }, operations);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST")
      writes.push({ path, body: request.postDataJSON() });
    if (path === "/api/v1/auth/config")
      return route.fulfill({ json: { shared_account: true } });
    if (path === "/api/v1/auth/me")
      return route.fulfill(
        signedIn
          ? { json: user }
          : { status: 401, json: { detail: "Sign in required" } },
      );
    if (path === "/api/v1/auth/identity/start")
      return route.fulfill({
        json: {
          authorization_url:
            "http://127.0.0.1:8500/api/v1/identity/auth?synthetic=1",
        },
      });
    if (path === "/api/v1/identity/auth")
      return route.fulfill({
        contentType: "text/html",
        body: "<h1>Onesa account</h1>",
      });
    if (path === "/api/v1/auth/workspaces")
      return route.fulfill({
        json: {
          workspaces:
            options.memberships === false
              ? []
              : [
                  { id: first, name: "Synthetic Berlin", role: "admin" },
                  { id: second, name: "Synthetic Hamburg", role: "admin" },
                ],
        },
      });
    if (path === "/api/v1/auth/workspace") {
      expect(request.headers()["x-csrf-token"]).toBe(user.csrf);
      user = {
        ...user,
        tenant_id: request.postDataJSON().tenant_id,
        csrf: "rotated-" + user.csrf,
      };
      return route.fulfill({ json: user });
    }
    if (path === "/api/v1/operations")
      return route.fulfill({ json: operations });
    if (path === "/api/v1/settings")
      return route.fulfill({
        json: {
          currency: "EUR",
          units: "metric",
          language: "en",
          region: "synthetic-campus",
        },
      });
    if (path === "/api/v1/users") return route.fulfill({ json: [] });
    if (path === "/api/v1/auth/logout") {
      signedIn = false;
      return route.fulfill({
        json: {
          ok: !options.partialLogout,
          shared_account: true,
          local_signed_out: true,
          central_signed_out: !options.partialLogout,
        },
      });
    }
    throw new Error(`Unexpected synthetic request ${request.method()} ${path}`);
  });
  return writes;
}

test("public sign-in shows separate mobile release availability without sending visitors to an unpublished app", async ({ page }) => {
  await identityUI(page);
  await page.goto("/");
  const downloads = page.getByRole("region", { name: "Onesa Drone mobile downloads" });
  await expect(downloads).toBeVisible();
  for (const platform of ["ios", "android"] as const) {
    const label = platform === "ios" ? "iOS" : "Android";
    const href = storeListing(platform, mobileListings[platform]);
    const link = downloads.getByRole("link", { name: "Download Onesa Drone for " + label });
    if (href) {
      await expect(link).toHaveAttribute("href", href);
    } else {
      await expect(downloads.getByText(label + " · Unavailable")).toBeVisible();
      await expect(link).toHaveCount(0);
    }
  }
});

test("shared sign-in has one clear entry and no second account form", async ({
  page,
}) => {
  const writes = await identityUI(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "One account. Every Onesa application.",
    }),
  ).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Continue with Onesa" }),
  ).toBeVisible();
  const button = await page
    .getByRole("button", { name: "Continue with Onesa" })
    .boundingBox();
  expect(button!.y + button!.height).toBeLessThan(644);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.screenshot({
      path: test.info().outputPath(`shared-sign-in-${colorScheme}-390.png`),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Continue with Onesa" }).click();
  await expect(
    page.getByRole("heading", { name: "Onesa account" }),
  ).toBeVisible();
  expect(writes).toEqual([
    { path: "/api/v1/auth/identity/start", body: { reauthenticate: false } },
  ]);
});

test("global administrator explicitly chooses a workspace and can switch it", async ({
  page,
}) => {
  const writes = await identityUI(page, { signedIn: true });
  await page.setViewportSize({ width: 1280, height: 840 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Choose your workspace" }),
  ).toBeVisible();
  await expect(
    page.getByText("Onesa administrator · All applications"),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("workspace-choice-1280.png"),
    fullPage: true,
  });
  await expect(
    page.getByRole("button", { name: "Open workspace", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Workspace", { exact: true }).selectOption(first);
  await page
    .getByRole("button", { name: "Open workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Mission overview", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Administration", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Manage Onesa accounts" }),
  ).toBeVisible();
  await expect(page.getByLabel("Initial password")).toHaveCount(0);
  await page.getByRole("button", { name: "Switch workspace" }).click();
  await page.getByLabel("Workspace", { exact: true }).selectOption(second);
  await page
    .getByRole("button", { name: "Open workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Mission overview", exact: true }),
  ).toBeVisible();
  expect(writes.map((entry) => entry.body)).toEqual([
    { tenant_id: first },
    { tenant_id: second },
  ]);
  await expect(
    page.getByRole("button", { name: "Sign out of Onesa", exact: true }),
  ).toBeVisible();
});

test("missing workspace access is explained without asking for another signup", async ({
  page,
}) => {
  await identityUI(page, { signedIn: true, memberships: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Your account is ready" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Open workspace", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Account & application access" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
});

test("callback failure is readable and removes the transient query from browser history", async ({
  page,
}) => {
  await identityUI(page);
  await page.goto("/?account_error=identity_callback_invalid");
  await expect(page.getByRole("alert")).toContainText(
    "That sign-in link has expired",
  );
  await expect(page).toHaveURL(/\/$/);
  await expect(
    page.getByRole("button", { name: "Continue with Onesa" }),
  ).toBeEnabled();
});

test("administrator confirmation returns to the shared account with the existing CSRF proof", async ({
  page,
}) => {
  const writes = await identityUI(page, { signedIn: true });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Confirm administrator sign-in" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Onesa account" }),
  ).toBeVisible();
  expect(writes).toEqual([
    { path: "/api/v1/auth/identity/start", body: { reauthenticate: true } },
  ]);
});

test("partial central logout clears Drone and provides a direct account recovery link", async ({
  page,
}) => {
  await identityUI(page, { signedIn: true, partialLogout: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Sign out of Onesa", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "You are signed out of Drone",
  );
  await expect(
    page.getByRole("link", { name: "Open Onesa account", exact: true }),
  ).toHaveAttribute("href", account.account_url);
  await expect(
    page.getByRole("button", { name: "Continue with Onesa" }),
  ).toBeVisible();
  await expect(page.getByText(account.email)).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: test.info().outputPath("partial-sign-out-390.png"),
    fullPage: true,
  });
});
