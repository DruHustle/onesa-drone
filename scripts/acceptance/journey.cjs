const { chromium, expect, request } = require(process.env.PW_ROOT);
const assert = require("node:assert/strict");
const f = JSON.parse(process.env.LOCAL_FIXTURE);
const verifyMemberStatus = require("./member-status.cjs");
const fixtureNames = ["member", "admin"];
let step = "browser startup";
const receipt = (name) => console.log("PASS " + name);
function credentialRequest(request) {
  const url = new URL(request.url());
  return (
    url.origin === f.portal &&
    request.method() === "POST" &&
    /^\/api\/v1\/account\/interaction\/[A-Za-z0-9_-]+\/login$/.test(
      url.pathname,
    )
  );
}
async function submitPortalLogin(page) {
  const response = page.waitForResponse((result) =>
    credentialRequest(result.request()),
  );
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  return response;
}
(async () => {
  console.log("Browser runtime starting");
  for (const role of fixtureNames) {
    const browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_PATH,
      args: process.env.CHROMIUM_PATH
        ? [
            "--single-process",
            "--no-zygote",
            "--disable-gpu",
            "--disable-webgl",
            "--js-flags=--max-old-space-size=96",
          ]
        : [],
    });
    try {
      const context = await browser.newContext({
        ignoreHTTPSErrors: true,
        acceptDownloads: false,
        locale: "en-US",
      });
      const page = await context.newPage();
      page.setDefaultTimeout(30000);
      let credentialPosts = 0;
      page.on("request", (request) => {
        if (credentialRequest(request)) credentialPosts++;
      });
      for (const state of ["signed out", "active Portal"]) {
        const label = role + " / " + state;
        const postsBefore = credentialPosts;
        step = label + " / open Drone";
        await page.goto(f.drone);
        await page
          .getByRole("button", { name: /^(Continue|Sign in) with Onesa$/ })
          .click();
        step = label + " / enter Portal";
        if (state === "signed out")
          await page.waitForURL(
            (url) =>
              url.origin === f.portal &&
              url.pathname.startsWith("/account/sign-in/"),
            { timeout: 95000 },
          );
        if (state === "signed out") {
          await page
            .getByLabel("Email address", { exact: true })
            .fill(role + "@example.test");
          await page.getByLabel("Password", { exact: true }).fill(f.password);
          const factor = page.getByLabel("Authenticator or recovery code", {
            exact: true,
          });
          step = label + " / password submission";
          if (role === "admin" && (await factor.isVisible()))
            await factor.fill(f.codes.shift());
          let response = await submitPortalLogin(page);
          if (!response.ok() && role === "admin") {
            const problem = (await response.json()).error?.code;
            assert.equal(problem === "MFA_REQUIRED", true);
            step = label + " / verified MFA challenge";
            await factor.fill(f.codes.shift());
            response = await submitPortalLogin(page);
          }
          assert.equal(response.status(), 200);
        } else {
          await Promise.race([
            page.getByRole("button", { name: /^Continue as/ }).waitFor(),
            page
              .getByRole("heading", {
                name:
                  role === "admin"
                    ? "Choose your workspace"
                    : "Mission overview",
                exact: true,
              })
              .waitFor(),
          ]);
          if (new URL(page.url()).origin === f.portal) {
            await expect(
              page.getByRole("button", {
                name: new RegExp("^Continue as " + role),
              }),
            ).toBeVisible();
            await page
              .getByRole("button", { name: new RegExp("^Continue as " + role) })
              .click();
          }
        }
        step = label + " / complete Drone callback";
        await page.waitForURL(
          (url) =>
            url.origin === f.drone && url.pathname === "/" && !url.search,
          { timeout: 45000 },
        );
        if (role === "admin") {
          step = label + " / select approved workspace";
          await page
            .getByLabel("Workspace", { exact: true })
            .selectOption(f.tenant);
          await page
            .getByRole("button", { name: "Open workspace", exact: true })
            .click();
        }
        step = label + " / load workspace and read identity";
        await expect(
          page.getByRole("heading", { name: "Mission overview", exact: true }),
        ).toBeVisible({ timeout: 45000 });
        const central = await context.request.get(
          f.portal + "/api/v1/account/me",
        );
        assert.equal(central.status(), 200);
        const account = (await central.json()).account;
        assert.equal(account.id, f[role]);
        const me = await (
          await context.request.get(f.drone + "/api/v1/auth/me")
        ).json();
        assert.equal(me.identity_subject, account.id);
        assert.equal(me.tenant_id, f.tenant);
        assert.equal(me.role, role === "admin" ? "admin" : "operator");
        if (state === "active Portal")
          assert.equal(credentialPosts, postsBefore);
        receipt(label + " → Drone workspace and stable subject");
        if (state === "signed out") {
          // Start a fresh Drone session while keeping the Portal session in this browser.
          await context.clearCookies({ name: "drone_session" });
          continue;
        }
        if (role === "admin") {
          step = "admin preference write";
          await page
            .getByRole("button", { name: "Administration", exact: true })
            .click();
          await page.getByLabel("Currency").selectOption("GBP");
          const write = page.waitForResponse(
            (response) =>
              response.request().method() === "PUT" &&
              new URL(response.url()).pathname === "/api/v1/settings",
          );
          await page
            .getByRole("button", { name: "Save preferences", exact: true })
            .click();
          assert.equal((await write).status(), 200);
          await expect(page.getByRole("alert")).toContainText(
            "Operating preferences saved.",
          );
          const saved = await context.request.get(f.drone + "/api/v1/settings");
          assert.equal((await saved.json()).currency, "GBP");
          receipt(step + " verified by API readback");
          await verifyMemberStatus({
            page,
            request,
            expect,
            assert,
            fixture: f,
            progress: (action) => {
              step = action;
            },
          });
          receipt(
            "Portal admin disable/restore: live member denied, old grant stays invalid, fresh operator keeps the same workspace and is denied the other organization",
          );
        } else {
          step = "operator delivery / authorization";
          await page.getByRole("button", { name: "+ New delivery" }).click();
          await page
            .getByLabel("Delivery reference")
            .fill("Acceptance synthetic parcel");
          const created = page.waitForResponse(
            (r) =>
              new URL(r.url()).pathname === "/api/v1/missions" &&
              r.request().method() === "POST",
          );
          await page.getByRole("button", { name: "Register delivery" }).click();
          assert.equal((await created).status(), 201);
          const headers = { Origin: f.drone, "X-CSRF-Token": me.csrf };
          assert.equal(
            (
              await context.request.put(f.drone + "/api/v1/settings", {
                headers,
                data: {
                  currency: "GBP",
                  units: "metric",
                  language: "en",
                  region: "fixture",
                },
              })
            ).status(),
            403,
          );
          assert.equal(
            (
              await context.request.post(f.drone + "/api/v1/auth/workspace", {
                headers,
                data: { tenant_id: f.other },
              })
            ).status(),
            403,
          );
          receipt(
            "operator delivery 201; admin preference write 403; foreign workspace select 403",
          );
        }
        if (role === "member") {
          step = "authenticated Portal deletion request";
          await page.goto(f.portal + "/account");
          await page
            .getByRole("link", {
              name: "Request account deletion",
              exact: true,
            })
            .click();
          await page.getByRole("checkbox").check();
          await page
            .getByRole("button", {
              name: "Submit deletion request",
              exact: true,
            })
            .click();
          await expect(page.getByRole("status")).toContainText(
            "Your request was recorded",
          );
          receipt(
            "authenticated Portal privacy intake recorded a synthetic request",
          );
        }
        step = "sign out";
        await page.goto(f.drone);
        await page
          .getByRole("button", { name: "Sign out of Onesa", exact: true })
          .click();
        await expect(
          page.getByRole("button", { name: /^(Continue|Sign in) with Onesa$/ }),
        ).toBeVisible();
        assert.equal(
          (await context.request.get(f.drone + "/api/v1/auth/me")).status(),
          401,
        );
        receipt(role + " sign-out invalidates Drone session");
      }
      await context.close();
    } finally {
      await browser.close();
    }
  }
})().catch((e) => {
  // Assertion and navigation messages can contain complete callback URLs or cookies.
  console.error("FAILED " + step + " [" + e.name + "]");
  process.exitCode = 1;
});
