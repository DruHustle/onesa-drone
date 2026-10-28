import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createRequire } from "node:module";
import {
  installAutomationSession,
  assertFixtureOrigin,
} from "./probe_policy.mjs";
const require = createRequire(
  new URL("../../frontend/package.json", import.meta.url),
);
const { request } = require("@playwright/test");

test("fixture credentials require the exact origin", () => {
  const origin = "https://drone-staging.onesa.eu";
  assert.doesNotThrow(() => assertFixtureOrigin(origin + "/", origin));
  for (const url of [
    "https://vercel.com/login",
    "https://drone-staging.onesa.eu.attacker.test/",
    "http://drone-staging.onesa.eu/",
    "https://drone-staging.onesa.eu:444/",
    "https://drone-staging.onesa.eu@attacker.test/",
  ])
    assert.throws(
      () => assertFixtureOrigin(url, origin),
      /before entering credentials/,
    );
});

test("a real redirect cannot forward automation access to another origin", async () => {
  let foreignRequests = 0;
  const foreign = http.createServer((_req, res) => {
    foreignRequests++;
    res.end("foreign");
  });
  const local = http.createServer((req, res) => {
    assert.equal(req.headers["x-vercel-protection-bypass"], "synthetic-secret");
    res.writeHead(302, {
      Location: `http://127.0.0.1:${foreign.address().port}/login`,
    });
    res.end();
  });
  await new Promise((resolve) => foreign.listen(0, "127.0.0.1", resolve));
  await new Promise((resolve) => local.listen(0, "127.0.0.1", resolve));
  const api = await request.newContext();
  try {
    const origin = `http://127.0.0.1:${local.address().port}`;
    await assert.rejects(
      installAutomationSession({ request: api }, origin, "synthetic-secret"),
      /before entering credentials/,
    );
    assert.equal(foreignRequests, 0);
  } finally {
    await api.dispose();
    await Promise.all([
      new Promise((r) => local.close(r)),
      new Promise((r) => foreign.close(r)),
    ]);
  }
});

test("returned cookies are rebound to the exact host and no browser headers are set", async () => {
  let cleared = false,
    installed;
  const context = {
    request: {
      get: async (_url, options) => {
        assert.equal(options.maxRedirects, 0);
        return { status: () => 307, headers: () => ({ location: "/" }) };
      },
    },
    cookies: async () => [
      {
        name: "_vercel_jwt",
        value: "synthetic",
        secure: true,
        domain: ".onesa.eu",
      },
    ],
    clearCookies: async () => {
      cleared = true;
    },
    addCookies: async (cookies) => {
      installed = cookies;
    },
  };
  const origin = "https://drone-staging.onesa.eu";
  await installAutomationSession(context, origin, "synthetic-secret");
  assert.equal(cleared, true);
  assert.deepEqual(installed, [
    {
      name: "_vercel_jwt",
      value: "synthetic",
      url: origin,
      secure: true,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await assert.rejects(
    installAutomationSession(
      { ...context, cookies: async () => [] },
      origin,
      "synthetic-secret",
    ),
    /did not establish/,
  );
  await installAutomationSession({}, origin, undefined);
});
