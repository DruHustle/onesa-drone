import { test, expect, type Page } from "@playwright/test";

async function syntheticSessions(page: Page) {
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    let session = "",
      logins = 0;
    const streams: EventTarget[] = [];
    const advisories: Array<(response: Response) => void> = [];
    class SyntheticStream extends EventTarget {
      onerror = null;
      constructor() {
        super();
        streams.push(this);
      }
      close() {}
    }
    Object.defineProperty(window, "EventSource", { value: SyntheticStream });
    Object.assign(window, {
      syntheticStreamCount: () => streams.length,
      syntheticAdvisoryCount: () => advisories.length,
      expireSyntheticSession: () => {
        session = "";
        streams.at(-1)?.dispatchEvent(new Event("expired"));
      },
      expirePreviousSyntheticStream: () =>
        streams[0]?.dispatchEvent(new Event("expired")),
    });
    window.fetch = async (input, init) => {
      const url = new URL(
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url,
        location.href,
      );
      if (
        url.origin !== location.origin ||
        !url.pathname.startsWith("/api/v1/")
      )
        return nativeFetch(input, init);
      const json = (value: unknown, status = 200) =>
        new Response(JSON.stringify(value), {
          status,
          headers: { "Content-Type": "application/json" },
        });
      switch (url.pathname) {
        case "/api/v1/auth/login":
          session = ++logins === 1 ? "a" : "b";
          return json({
            id: session,
            email: `session-${session}@example.test`,
            role: "admin",
            tenant_id: session,
            csrf: `synthetic-${session}`,
          });
        case "/api/v1/auth/logout":
          session = "";
          return json({ ok: true });
        case "/api/v1/auth/me":
          return json({ detail: "Sign in required" }, 401);
        case "/api/v1/operations":
          return json({
            aircraft: [],
            missions: [],
            counts: {},
            mode: "simulation",
            at: 0,
            truncated: { aircraft: false, missions: false },
          });
        case "/api/v1/settings":
          return json({
            currency: "EUR",
            units: "metric",
            language: "en",
            region: "synthetic-campus",
          });
        case "/api/v1/assistant":
          return new Promise<Response>((resolve) => {
            advisories.push(resolve);
            Object.assign(window, {
              releasePreviousAdvisory: () =>
                advisories[0](
                  json({
                    answer: "PREVIOUS_SESSION_PRIVATE_ADVISORY",
                    source: "synthetic-test",
                    provider_status: "not-configured",
                  }),
                ),
              releaseCurrentAdvisory: () =>
                advisories.at(-1)?.(
                  json({
                    answer: "CURRENT_SESSION_ADVISORY",
                    source: "synthetic-test",
                    provider_status: "not-configured",
                  }),
                ),
            });
          });
        default:
          throw new Error("Unexpected synthetic API route: " + url.pathname);
      }
    };
  });
  await page.goto("/");
}

async function signIn(page: Page, session: string) {
  await page
    .getByLabel("Email", { exact: true })
    .fill(`session-${session}@example.test`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Synthetic-session-only-password-42!");
  await page.getByRole("button", { name: /^Sign in/ }).click();
  await expect(page.locator("body")).toContainText(
    `session-${session}@example.test`,
  );
  await page.waitForFunction(
    (minimum) => (window as any).syntheticStreamCount() >= minimum,
    session === "a" ? 1 : 2,
  );
}

test("late advisory from a signed-out account never appears in the next account", async ({
  page,
}) => {
  await syntheticSessions(page);
  await signIn(page, "a");
  await page.getByRole("button", { name: "AI assistant", exact: true }).click();
  await page.getByLabel("Your question").fill("Explain synthetic operations.");
  await page
    .getByRole("button", { name: "Ask assistant", exact: true })
    .click();
  await page.waitForFunction(
    () => typeof (window as any).releasePreviousAdvisory === "function",
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signIn(page, "b");
  await page.getByRole("button", { name: "AI assistant", exact: true }).click();
  await page
    .getByLabel("Your question")
    .fill("Explain this account's synthetic operations.");
  await page
    .getByRole("button", { name: "Ask assistant", exact: true })
    .click();
  await page.waitForFunction(
    () => (window as any).syntheticAdvisoryCount() === 2,
  );
  await page.evaluate(async () => {
    (window as any).releasePreviousAdvisory();
    // The synthetic response body is in memory. A new event-loop turn observes
    // the real application's completed promise chain without a network delay.
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  await expect(page.locator("body")).not.toContainText(
    "PREVIOUS_SESSION_PRIVATE_ADVISORY",
  );
  await expect(
    page.getByRole("button", { name: "Reviewing context…", exact: true }),
  ).toBeDisabled();
  await page.evaluate(() => (window as any).releaseCurrentAdvisory());
  await expect(page.locator(".assistant-answer")).toContainText(
    "CURRENT_SESSION_ADVISORY",
  );
  await expect(
    page.getByRole("button", { name: "Ask assistant", exact: true }),
  ).toBeEnabled();
});

test("expiry clears an open account-specific draft before a different sign-in", async ({
  page,
}) => {
  await syntheticSessions(page);
  await signIn(page, "a");
  await page
    .getByRole("button", { name: "+ Register aircraft", exact: true })
    .click();
  await page
    .getByLabel("Aircraft identifier")
    .fill("PREVIOUS_SESSION_PRIVATE_DRAFT");
  await page.evaluate(() => (window as any).expireSyntheticSession());
  await signIn(page, "b");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText(
    "PREVIOUS_SESSION_PRIVATE_DRAFT",
  );
});

test("a queued expiry from the closed old stream cannot sign out the next account", async ({
  page,
}) => {
  await syntheticSessions(page);
  await signIn(page, "a");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signIn(page, "b");
  await page.evaluate(() => (window as any).expirePreviousSyntheticStream());
  await expect(page.locator("body")).toContainText("session-b@example.test");
  await expect(page.getByRole("button", { name: /^Sign in/ })).toHaveCount(0);
});
