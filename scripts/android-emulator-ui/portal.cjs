// Drive only the real browser's loopback Portal form. The app tap, Android
// callback dispatch and signed-in workspace assertion run through Android UI.
const { chromium } = require("../../frontend/node_modules/@playwright/test");
const [role, state] = process.argv.slice(2);
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let stage = 1;
const observations = new Set();
async function verify() {
  if (!["member", "admin"].includes(role) || !["active", "signed-out"].includes(state)) throw Error();
  const origin = "https://localhost:54843";
  const port = Number(process.env.CHROME_DEVTOOLS_PORT);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535) throw Error();
  const available = Date.now() + (state === "active" ? 18000 : 55000);
  let browser, page;
  while (Date.now() < available && !page) {
    try {
      if (browser && !browser.isConnected()) {
        observations.add("cdp-disconnected");
        browser = undefined;
      }
      browser ||= await chromium.connectOverCDP("http://127.0.0.1:" + port, { timeout: 3500 });
      observations.add("cdp-connected");
      const pages = browser.contexts().flatMap((c) => c.pages()).filter((p) => !p.isClosed());
      for (const candidate of pages.slice().reverse()) {
        let url;
        try { url = new URL(candidate.url()); } catch { observations.add("other-page"); continue; }
        if (url.origin === origin && url.pathname.startsWith("/account/sign-in/")) {
          observations.add("portal-sign-in"); page = candidate; break;
        }
        observations.add(url.origin === origin ? "portal-other-page" :
          url.protocol === "chrome-error:" ? "browser-error-page" :
          url.protocol === "onesadrone:" ? "native-callback" : "other-page");
      }
    } catch { browser = undefined; }
    if (!page) await pause(400);
  }
  // A valid active session can redirect straight back to the OS before CDP attaches.
  // The caller wiped native storage and independently requires the expected role.
  if (!page && state === "active") return;
  if (!page) throw Error();
  page.setDefaultTimeout(18000);
  stage = 2;
  if (state === "active") {
    const active = page.getByRole("button", { name: new RegExp("^Continue as " + role) });
    await active.click();
    return;
  }
  await page.getByLabel("Email address", { exact: true }).fill(role + "@example.test");
  await page.getByLabel("Password", { exact: true }).fill(process.env.ONESA_FIXTURE_PASSWORD);
  const factor = page.getByLabel("Authenticator or recovery code", { exact: true });
  if (role === "admin" && await factor.isVisible()) await factor.fill(process.env.ONESA_FIXTURE_FACTOR);
  async function submit() {
    const response = page.waitForResponse((r) => {
      const u = new URL(r.url());
      return u.origin === origin && /^\/api\/v1\/account\/interaction\/[A-Za-z0-9_-]+\/login$/.test(u.pathname)
        && r.request().method() === "POST";
    });
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    return response;
  }
  stage = 3;
  let result = await submit();
  if (!result.ok() && role === "admin" && (await result.json()).error?.code === "MFA_REQUIRED") {
    stage = 4;
    await factor.fill(process.env.ONESA_FIXTURE_FACTOR);
    result = await submit();
  }
  if (!result.ok()) throw Error();
}
// No raw CDP URL, account value, credential, callback or browser diagnostic is emitted.
verify().then(() => process.exit(0), () => {
  console.log(JSON.stringify([...observations]));
  process.exit(stage);
});
