import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function login(page: Page, account: string) {
  await page.goto("/");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`browser-nvidia-${account}@example.test`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Synthetic-browser-password-42!");
  await page.getByRole("button", { name: "Sign in", exact: false }).click();
  await expect(
    page.getByRole("heading", { name: "Mission overview", exact: true }),
  ).toBeVisible();
}
const ready = (page: Page) =>
  expect(page.getByTestId("reference-status")).toHaveText(
    "3/3 NVIDIA models loaded",
  );
async function disableGraphics(page: Page) {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      value: function (kind: string, ...args: unknown[]) {
        if (kind.includes("webgl") && !(window as any).allowTestGraphics)
          return null;
        return (original as any).call(this, kind, ...args);
      },
    });
  });
}

test("NVIDIA models load automatically, render and disclose provenance without mission writes", async ({
  page,
}) => {
  const writes: string[] = [],
    errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method()))
      writes.push(new URL(request.url()).pathname);
  });
  await login(page, "load");
  await ready(page);
  await page.getByLabel("Camera", { exact: true }).selectOption("environment");
  await expect(page.locator(".scene canvas")).toBeVisible();
  await page
    .getByText("NVIDIA environment models · source and previews", {
      exact: true,
    })
    .click();
  await expect(page.locator(".reference-model-grid article")).toHaveCount(3);
  await expect(
    page.getByRole("link", { name: "Original source", exact: true }),
  ).toHaveCount(3);
  await expect(page.locator(".reference-library")).toContainText(
    "do not add flight physics",
  );
  await page.screenshot({
    path: "../artifacts/nvidia-environment-desktop.png",
    fullPage: true,
  });
  await page.getByLabel("Camera", { exact: true }).selectOption("orbit");
  const canvas = page.locator(".scene canvas");
  await canvas.focus();
  await expect(canvas).toBeFocused();
  const before = await canvas.screenshot();
  await page.keyboard.press("ArrowRight");
  await expect(async () => {
    expect((await canvas.screenshot()).equals(before)).toBe(false);
  }).toPass();
  expect(writes).toEqual(["/api/v1/auth/login"]);
  expect(errors).toEqual([]);
});

test("a failed model keeps the campus usable and retries cleanly", async ({
  page,
}) => {
  await page.route("**/models/nvidia/nvidia-mobile-cart/*.glb", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await login(page, "failure");
  await expect(page.getByTestId("reference-status")).toHaveText(
    "2/3 NVIDIA models loaded; static previews available",
  );
  await expect(page.locator(".scene canvas")).toBeVisible();
  await page.unroute("**/models/nvidia/nvidia-mobile-cart/*.glb");
  await page.getByRole("button", { name: "Retry environment models" }).click();
  await ready(page);
});

test("a damaged model is rejected and can be recovered", async ({ page }) => {
  await page.route(
    "**/models/nvidia/nvidia-transfer-conveyor/*.glb",
    async (route) => {
      const response = await route.fetch();
      const bytes = await response.body();
      bytes[bytes.length - 1] ^= 1;
      await route.fulfill({ response, body: bytes });
    },
  );
  await login(page, "integrity");
  await expect(page.getByTestId("reference-status")).toHaveText(
    "2/3 NVIDIA models loaded; static previews available",
  );
  await page.unroute("**/models/nvidia/nvidia-transfer-conveyor/*.glb");
  await page.getByRole("button", { name: "Retry environment models" }).click();
  await ready(page);
});

test("no WebGL shows real static previews and the retry can restore 3D", async ({
  page,
}) => {
  await disableGraphics(page);
  await login(page, "no-webgl");
  await expect(page.locator(".scene-fallback")).toBeVisible();
  await expect(page.locator(".reference-fallback-images img")).toHaveCount(3);
  await expect(page.getByLabel("Camera", { exact: true })).toBeVisible();
  await page.evaluate(() => {
    (window as any).allowTestGraphics = true;
  });
  await page.getByRole("button", { name: "Retry 3D view" }).click();
  await ready(page);
  await expect(page.locator(".scene-fallback")).toHaveCount(0);
});

test("graphics-context loss shows previews and context restoration rebuilds the scene", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page, "context");
  await ready(page);
  await page.locator(".scene canvas").evaluate((canvas) => {
    const context = (canvas as HTMLCanvasElement).getContext("webgl2")!;
    const extension = context.getExtension("WEBGL_lose_context")!;
    (window as any).restoreTestContext = () => extension.restoreContext();
    extension.loseContext();
  });
  await expect(page.locator(".scene-fallback")).toBeVisible();
  await page.evaluate(() => (window as any).restoreTestContext());
  await ready(page);
  await expect(page.locator(".scene-fallback")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("leaving a scene cancels pending downloads and a fresh scene loads normally", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let release!: () => void;
  const paused = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/models/nvidia/**/*.glb", async (route) => {
    await paused;
    await route.continue().catch(() => {});
  });
  await login(page, "cancel");
  await expect(page.getByTestId("reference-status")).toContainText("Loading");
  await page.getByRole("button", { name: "AI assistant", exact: true }).click();
  await expect(page.locator(".scene-shell")).toHaveCount(0);
  release();
  await page.unroute("**/models/nvidia/**/*.glb");
  await page.getByRole("button", { name: "Dashboard", exact: true }).click();
  await ready(page);
  expect(errors).toEqual([]);
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`${colorScheme} mobile fallback, keyboard provenance and accessibility`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    await disableGraphics(page);
    await login(page, `mobile-${colorScheme}`);
    const summary = page.locator(".reference-library summary");
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("heading", { name: "Transfer conveyor", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    const fallback = page.locator(".scene-fallback");
    const box = await fallback.boundingBox();
    const retry = await page
      .getByRole("button", { name: "Retry 3D view" })
      .boundingBox();
    expect(retry!.y + retry!.height).toBeLessThanOrEqual(box!.y + box!.height);
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      axe.violations.map((violation) => ({
        id: violation.id,
        targets: violation.nodes.map((node) => node.target),
      })),
    ).toEqual([]);
    await page.emulateMedia({ forcedColors: "active" });
    await expect(summary).toBeVisible();
    await page.screenshot({
      path: `../artifacts/nvidia-fallback-mobile-${colorScheme}.png`,
      fullPage: true,
    });
  });
}
