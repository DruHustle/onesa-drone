import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Layout and keyboard acceptance only. Every API response and telemetry event is
// synthetic; no backend, model, WebGL, hosted or physical-flight claim is made.
const operations = {
  aircraft: [],
  missions: [],
  counts: {},
  mode: "simulation",
  at: 0,
  truncated: { aircraft: false, missions: false },
};
const unexpected = new WeakMap<Page, string[]>();

test.beforeEach(async ({ page, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  expect(["127.0.0.1", "localhost"]).toContain(new URL(origin).hostname);
  const requests: string[] = [];
  unexpected.set(page, requests);
  await page.addInitScript((value) => {
    class SyntheticNavigationStream extends EventTarget {
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
    Object.defineProperty(window, "EventSource", {
      value: SyntheticNavigationStream,
    });
    const nativeContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (kind, ...args) {
      if (["webgl", "webgl2", "experimental-webgl"].includes(kind)) return null;
      return Reflect.apply(nativeContext, this, [kind, ...args]);
    } as typeof nativeContext;
  }, operations);
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) {
      requests.push(`External request: ${url.origin}`);
      return route.abort("blockedbyclient");
    }
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const values: Record<string, unknown> = {
      "/api/v1/auth/me": {
        id: "synthetic-navigation-user",
        email: "synthetic-navigation@example.test",
        role: "operator",
        tenant_id: "synthetic-navigation-tenant",
        csrf: "synthetic-navigation-only",
      },
      "/api/v1/operations": operations,
      "/api/v1/settings": {
        currency: "EUR",
        units: "metric",
        language: "en",
        region: "synthetic-campus",
      },
    };
    if (request.method() !== "GET" || !(url.pathname in values)) {
      requests.push(`${request.method()} ${url.pathname}`);
      return route.fulfill({
        status: 503,
        json: { detail: "Unexpected synthetic navigation request" },
      });
    }
    await route.fulfill({ json: values[url.pathname] });
  });
});

test.afterEach(async ({ page }) => {
  expect(unexpected.get(page)).toEqual([]);
});

async function workspace(page: Page, width = 390) {
  await page.setViewportSize({ width, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Mission overview", exact: true }),
  ).toBeVisible();
}

async function destination(page: Page, name: string) {
  const toggle = page.getByRole("button", { name: "Toggle navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await page.getByRole("button", { name, exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
}

test("closed mobile navigation is absent from keyboard and accessibility navigation", async ({
  page,
}) => {
  await workspace(page);
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  await expect(page.locator(".sidebar")).toBeHidden();
  const toggle = page.getByRole("button", { name: "Toggle navigation" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(() => {
        const active = document.activeElement;
        if (!active || active === document.body) return true;
        const rect = active.getBoundingClientRect();
        return (
          !active.closest(".sidebar") &&
          rect.left >= 0 &&
          rect.right <= innerWidth &&
          rect.top >= 0 &&
          rect.bottom <= innerHeight
        );
      }),
    ).toBe(true);
  }
});

test("drawer opens with usable controls, contains focus and closes by each dismissal", async ({
  page,
}) => {
  await workspace(page);
  const toggle = page.getByRole("button", { name: "Toggle navigation" });
  const toggleBox = await toggle.boundingBox();
  expect(toggleBox!.height).toBeGreaterThanOrEqual(44);
  expect(toggleBox!.width).toBeGreaterThanOrEqual(44);
  await toggle.click();
  const drawer = page.getByRole("dialog", { name: "Workspace navigation" });
  const close = drawer.getByRole("button", { name: "Close navigation" });
  await expect(drawer).toBeVisible();
  await expect(close).toBeFocused();
  for (const item of await drawer.locator("button, summary, .wordmark").all()) {
    const box = await item.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    expect(box!.width).toBeGreaterThanOrEqual(44);
  }
  await drawer.getByRole("link", { name: "ONESA DRONE" }).focus();
  await page.keyboard.press("Shift+Tab");
  await expect(drawer.getByRole("button", { name: "Sign out" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(drawer.getByRole("link", { name: "ONESA DRONE" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();
  await toggle.click();
  await close.click();
  await expect(drawer).toBeHidden();
  await expect(toggle).toBeFocused();
  await toggle.click();
  await page.mouse.click(385, 60);
  await expect(drawer).toBeHidden();
  await expect(toggle).toBeFocused();
});

test("drawer preserves an existing draft and blocks background focus and actions", async ({
  page,
}) => {
  await workspace(page);
  await destination(page, "AI assistant");
  const question = page.getByLabel("Your question");
  await question.fill("Retain this synthetic navigation draft.");
  const original = await question.elementHandle();
  const toggle = page.getByRole("button", { name: "Toggle navigation" });
  await toggle.click();
  const drawer = page.getByRole("dialog", { name: "Workspace navigation" });
  await expect(drawer).toBeVisible();
  await question.evaluate((node) => node.focus());
  await expect(
    drawer.getByRole("button", { name: "Close navigation" }),
  ).toBeFocused();
  // Role queries inspect the DOM, including native-dialog background content.
  // Assert the browser's modal state and actual rejected focus above instead.
  expect(await drawer.evaluate((node) => node.matches(":modal"))).toBe(true);
  await page
    .getByRole("button", { name: "Ask assistant", exact: true })
    .evaluate((node) => node.focus());
  await expect(
    drawer.getByRole("button", { name: "Close navigation" }),
  ).toBeFocused();
  // Enter acts on the actual focused Close control, never the background submit.
  // The fixture also rejects and reports every attempted API write.
  await page.keyboard.press("Enter");
  await expect(drawer).toBeHidden();
  await expect(question).toHaveValue("Retain this synthetic navigation draft.");
  expect(await original!.evaluate((node) => node.isConnected)).toBe(true);
  await expect(toggle).toBeFocused();
  await toggle.click();
  await drawer.getByRole("button", { name: "Aircraft", exact: true }).click();
  await expect(drawer).toBeHidden();
  await expect(
    page.getByRole("heading", { name: "Aircraft", exact: true }),
  ).toBeFocused();
});

test("850px responsive transitions preserve form nodes and move only navigation focus", async ({
  page,
}) => {
  await workspace(page, 1100);
  await destination(page, "AI assistant");
  const question = page.getByLabel("Your question");
  await question.fill("Preserve this draft across the navigation breakpoint.");
  const original = await question.elementHandle();
  await question.focus();
  await page.setViewportSize({ width: 850, height: 844 });
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  await expect(question).toBeFocused();
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await expect(
    page.getByRole("dialog", { name: "Workspace navigation" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 851, height: 844 });
  await expect(
    page.getByRole("dialog", { name: "Workspace navigation" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "AI assistant", exact: true }),
  ).toBeFocused();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 850, height: 844 });
  const toggle = page.getByRole("button", { name: "Toggle navigation" });
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(question).toHaveValue(
    "Preserve this draft across the navigation breakpoint.",
  );
  expect(await original!.evaluate((node) => node.isConnected)).toBe(true);
});

test("an open delivery dialog and its draft survive responsive navigation changes", async ({
  page,
}) => {
  await workspace(page, 1100);
  await page
    .getByRole("button", { name: "+ New delivery", exact: true })
    .click();
  const reference = page.getByLabel("Delivery reference");
  await reference.fill("Synthetic delivery draft stays here");
  const original = await reference.elementHandle();
  for (const width of [850, 390, 851, 1100]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(reference).toBeFocused();
    await expect(reference).toHaveValue("Synthetic delivery draft stays here");
    expect(await original!.evaluate((node) => node.isConnected)).toBe(true);
  }
});

test("small-screen drawer respects both color schemes, reduced motion and forced colors", async ({
  page,
}, testInfo) => {
  await workspace(page, 320);
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    await page.getByRole("button", { name: "Toggle navigation" }).click();
    const drawer = page.getByRole("dialog", { name: "Workspace navigation" });
    await expect(drawer).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(result.violations.map((item) => item.id)).toEqual([]);
    await testInfo.attach(`synthetic-navigation-320-${colorScheme}`, {
      body: await page.screenshot(),
      contentType: "image/png",
    });
    await page.keyboard.press("Escape");
  }
  await page.emulateMedia({ forcedColors: "active" });
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await expect(
    page.getByRole("button", { name: "Close navigation" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Toggle navigation" }),
  ).toBeFocused();
});
