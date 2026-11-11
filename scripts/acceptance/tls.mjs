import https from "node:https";
import { createRequire } from "node:module";
const portalProxy = createRequire(import.meta.url)(resolve("portal-proxy.cjs"));
import { Readable } from "node:stream";
import http from "node:http";
import { readFileSync, createReadStream, statSync } from "node:fs";
import { resolve, extname, sep } from "node:path";
const tls = {
  key: readFileSync("fixture.key"),
  cert: readFileSync("fixture.crt"),
};
for (const [port, target] of [
  [54843, 58300],
  [54844, 58400],
]) {
  https
    .createServer(tls, async (req, res) => {
      const url = new URL(req.url, "https://localhost");
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
          '<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="/assets/account.css"></head><body><main id="root"></main><script src="/assets/account.js"></script></body></html>',
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
          res.writeHead(remote.statusCode, remote.headers);
          remote.pipe(res);
          res.on("close", () => remote.destroy());
        },
      );
      proxy.on("error", () => {
        if (!res.headersSent) res.writeHead(502);
        res.end();
      });
      req.pipe(proxy);
    })
    .listen(port, "127.0.0.1");
}
