import https from "node:https";
import { createRequire } from "node:module";
const portalProxy = createRequire(import.meta.url)(resolve("portal-proxy.cjs"));
import { Readable } from "node:stream";
import http from "node:http";
import { spawnSync } from "node:child_process";
import {
  readFileSync,
  createReadStream,
  statSync,
  writeFileSync,
} from "node:fs";
import { resolve, extname, sep } from "node:path";
const tls = {
  key: readFileSync("fixture.key"),
  cert: readFileSync("fixture.crt"),
};
const nativeFlows = [];
let unexpectedCredentialRoute = false;
let fixtureExpirations = 0;
let expiredAccountResponses = 0;
let verifiedWarmSubjects = 0;
let warmSubjectVerificationFailed = false;
// Separate transport observations from the successful authorization audit.
// No URL, request body, header, identity or upstream error is retained.
const nativeStartDiagnostics = {
  version: 1, attempts: 0, responses200: 0, responsesOther2xx: 0,
  responses3xx: 0, responses4xx: 0, responses5xx: 0,
  responsesOther: 0, proxyErrors: 0,
};
function saveNativeStartDiagnostics() {
  if (!process.env.ONESA_NATIVE_START_DIAGNOSTICS_PATH) return;
  writeFileSync(process.env.ONESA_NATIVE_START_DIAGNOSTICS_PATH,
    JSON.stringify(nativeStartDiagnostics), { mode: 0o600 });
}
function recordNativeStart(key) {
  nativeStartDiagnostics[key] = Math.min(999, nativeStartDiagnostics[key] + 1);
  saveNativeStartDiagnostics();
}
saveNativeStartDiagnostics();
function saveNativeAudit() {
  if (process.env.ONESA_NATIVE_AUDIT_PATH)
    writeFileSync(
      process.env.ONESA_NATIVE_AUDIT_PATH,
      JSON.stringify({
        flows: nativeFlows,
        unexpectedCredentialRoute,
        fixtureExpirations,
        expiredAccountResponses,
        verifiedWarmSubjects,
        warmSubjectVerificationFailed,
      }),
      { mode: 0o600 },
    );
}
function recordNativeCredentialRoute(req, url) {
  if (!process.env.ONESA_NATIVE_AUDIT_PATH || req.method !== "POST") return;
  const match =
    /^\/api\/v1\/account\/interaction\/[A-Za-z0-9_-]+\/(login|continue)$/.exec(
      url.pathname,
    );
  if (!match) return;
  const entry = nativeFlows.at(-1);
  if (entry)
    entry[match[1] === "login" ? "credentialPosts" : "continuePosts"]++;
  else unexpectedCredentialRoute = true;
  saveNativeAudit();
}
for (const [port, target] of [
  [54843, 58300],
  [54844, 58400],
]) {
  https
    .createServer(tls, async (req, res) => {
      const url = new URL(req.url, "https://localhost");
      const nativeStart = port === 54844 && req.method === "POST" &&
        url.pathname === "/api/v1/auth/mobile/start";
      if (nativeStart) recordNativeStart("attempts");
      if (
        port === 54844 &&
        url.pathname === "/__onesa_fixture/expire-product-session"
      ) {
        const key = process.env.ONESA_NATIVE_CONTROL_KEY;
        const role = req.headers["x-onesa-fixture-role"];
        if (
          !key ||
          fixtureExpirations >= 2 ||
          req.method !== "POST" ||
          req.headers["x-onesa-fixture-control"] !== key ||
          role !== ["member", "admin"][fixtureExpirations] ||
          Number(req.headers["content-length"] || 0) !== 0 ||
          req.headers["transfer-encoding"]
        ) {
          res.writeHead(404).end();
          return;
        }
        const expiry = spawnSync(
          process.env.FIXTURE_PYTHON,
          [process.env.FIXTURE_EXPIRY_SCRIPT, role, "expire"],
          {
            env: process.env,
            encoding: "utf8",
            timeout: 10000,
            maxBuffer: 4096,
          },
        );
        if (expiry.status !== 0) {
          res.writeHead(409).end('{"error":"fixture-session-expiry-refused"}');
          return;
        }
        fixtureExpirations++;
        saveNativeAudit();
        res.setHeader("content-type", "application/json");
        res.writeHead(200).end(expiry.stdout);
        return;
      }
      if (port === 54843) recordNativeCredentialRoute(req, url);
      if (port === 54843 && !url.pathname.startsWith("/api/")) {
        if (
          url.pathname === "/assets/account.js" ||
          url.pathname === "/assets/account.css"
        ) {
          const css = url.pathname.endsWith(".css");
          res.setHeader(
            "content-type",
            css ? "text/css" : "application/javascript",
          );
          createReadStream(css ? "account.css" : "account.js").pipe(res);
          return;
        }
        res.setHeader("Content-Type", "text/html");
        res.end(
          '<!doctype html><html lang="en" data-onesa-product="company"><head><meta charset="utf-8"><meta name="color-scheme" content="light dark"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/assets/account.css"></head><body><main id="root"></main><script src="/assets/account.js"></script></body></html>',
        );
        return;
      }
      if (port === 54843) {
        const origin = process.env.PUBLIC_ORIGIN,
          nextUrl = new URL(req.url, origin);
        const headers = new Headers(req.headers);
        const body = ["GET", "HEAD"].includes(req.method)
          ? undefined
          : Readable.toWeb(req);
        const request = new Request(nextUrl, {
          headers,
          method: req.method,
          body,
          ...(body ? { duplex: "half" } : {}),
        });
        request.nextUrl = nextUrl;
        const dest = await portalProxy[req.method](request, {
          params: Promise.resolve({
            path: nextUrl.pathname.split("/").slice(3),
          }),
        });
        for (const [key, value] of dest.headers)
          if (key !== "set-cookie") res.setHeader(key, value);
        const cookies = dest.headers.getSetCookie();
        if (cookies.length) res.setHeader("set-cookie", cookies);
        res.writeHead(dest.status);
        if (dest.body) Readable.fromWeb(dest.body).pipe(res);
        else res.end();
        return;
      }
      if (port === 54844 && !url.pathname.startsWith("/api/")) {
        const base = process.env.STATIC;
        let file = resolve(base, "." + decodeURIComponent(url.pathname));
        if (file !== base && !file.startsWith(base + sep)) {
          res.writeHead(400).end();
          return;
        }
        try {
          if (!statSync(file).isFile()) file = resolve(base, "index.html");
        } catch {
          file = resolve(base, "index.html");
        }
        const mime = {
          ".html": "text/html",
          ".js": "application/javascript",
          ".css": "text/css",
          ".svg": "image/svg+xml",
          ".png": "image/png",
          ".webp": "image/webp",
          ".glb": "model/gltf-binary",
        };
        res.setHeader(
          "Content-Type",
          mime[extname(file)] || "application/octet-stream",
        );
        createReadStream(file).pipe(res);
        return;
      }
      const proxy = http.request(
        {
          hostname: "127.0.0.1",
          port: target,
          path: req.url,
          method: req.method,
          headers: {
            ...req.headers,
            ...(port === 54843
              ? { "x-portal-proxy-key": process.env.PORTAL_PROXY }
              : {}),
            "x-forwarded-proto": "https",
          },
        },
        (remote) => {
          if (nativeStart) {
            const status = remote.statusCode;
            recordNativeStart(status === 200 ? "responses200" :
              status >= 200 && status < 300 ? "responsesOther2xx" :
              status >= 300 && status < 400 ? "responses3xx" :
              status >= 400 && status < 500 ? "responses4xx" :
              status >= 500 && status < 600 ? "responses5xx" : "responsesOther");
          }
          if (
            port === 54844 &&
            req.method === "POST" &&
            url.pathname === "/api/v1/auth/mobile/start" &&
            remote.statusCode === 200 &&
            process.env.ONESA_NATIVE_AUDIT_PATH
          ) {
            nativeFlows.push({ credentialPosts: 0, continuePosts: 0 });
            saveNativeAudit();
          }
          if (
            port === 54844 &&
            req.method === "POST" &&
            url.pathname === "/api/v1/auth/mobile/exchange" &&
            remote.statusCode === 200 &&
            fixtureExpirations > verifiedWarmSubjects
          ) {
            const verified = spawnSync(
              process.env.FIXTURE_PYTHON,
              [
                process.env.FIXTURE_EXPIRY_SCRIPT,
                ["member", "admin"][fixtureExpirations - 1],
                "verify",
              ],
              {
                env: process.env,
                encoding: "utf8",
                timeout: 10000,
                maxBuffer: 4096,
              },
            );
            if (verified.status === 0) verifiedWarmSubjects++;
            else warmSubjectVerificationFailed = true;
            saveNativeAudit();
          }
          if (
            port === 54844 &&
            req.method === "GET" &&
            url.pathname === "/api/v1/auth/mobile/account" &&
            remote.statusCode === 401 &&
            fixtureExpirations > 0
          ) {
            expiredAccountResponses++;
            saveNativeAudit();
          }
          res.writeHead(remote.statusCode, remote.headers);
          remote.pipe(res);
          res.on("close", () => remote.destroy());
        },
      );
      proxy.on("error", () => {
        if (nativeStart) recordNativeStart("proxyErrors");
        if (!res.headersSent) res.writeHead(502);
        res.end();
      });
      req.pipe(proxy);
    })
    .listen(port, "127.0.0.1");
}
