import { test } from "node:test";
import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  writeFile,
  readFile,
  rm,
  symlink,
} from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { packageVercel } from "./vercel_package.mjs";

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), "onesa-drone-package-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const dist = join(root, "dist");
  await mkdir(join(dist, "assets"), { recursive: true });
  await writeFile(join(dist, "index.html"), '<div id="root"></div>');
  await writeFile(
    join(dist, "assets", "app-test.js"),
    "export const simulation=true;",
  );
  return {
    root,
    args: {
      dist,
      output: join(root, "release"),
      environment: "staging",
      backendOrigin: "https://drone-api-staging.onesa.eu",
      sourceCommit: "a".repeat(40),
      projectId: "prj_ObservedSyntheticFixture",
      orgId: "team_synthetic_fixture",
    },
  };
}

test("prebuilt routing keeps API before SPA and no private cache or indexing", async (t) => {
  const { args } = await fixture(t);
  const result = await packageVercel(args);
  const config = JSON.parse(
    await readFile(join(args.output, ".vercel/output/config.json")),
  );
  assert.equal(config.version, 3);
  assert.equal(
    config.routes[1].dest,
    "https://drone-api-staging.onesa.eu/api/$1",
  );
  assert.equal(config.routes[1].headers["Cache-Control"], "no-store");
  assert.match(config.routes[0].headers["X-Robots-Tag"], /noindex/);
  assert.equal(
    config.routes[2].headers["Cache-Control"],
    "public, max-age=31536000, immutable",
  );
  assert.equal(Object.keys(result.files).length, 2);
  assert.equal(
    await readFile(
      join(args.output, ".vercel/output/static/assets/app-test.js"),
      "utf8",
    ),
    "export const simulation=true;",
  );
  await assert.rejects(packageVercel(args), /EEXIST/);
});

test("foreign backend, environment swaps and missing source identities fail before output", async (t) => {
  const { args } = await fixture(t);
  for (const patch of [
    { backendOrigin: "http://localhost:8400" },
    { environment: "production" },
    { sourceCommit: "main" },
    { projectId: "invented" },
    { backendOrigin: "https://drone-api-staging.onesa.eu/extra" },
  ])
    await assert.rejects(packageVercel({ ...args, ...patch }));
});

test("hidden credentials and symlinks cannot enter a public artifact", async (t) => {
  const { args } = await fixture(t);
  await writeFile(join(args.dist, ".env"), "synthetic-private-fixture");
  await assert.rejects(packageVercel(args), /Hidden files/);
  await rm(join(args.dist, ".env"));
  await symlink("../index.html", join(args.dist, "assets/private-link.js"));
  await assert.rejects(packageVercel(args), /symlinks/);
});

test("production binds only its own backend and observed project", async (t) => {
  const { args } = await fixture(t);
  await packageVercel({
    ...args,
    environment: "production",
    backendOrigin: "https://drone-api.onesa.eu",
  });
  const config = JSON.parse(
    await readFile(join(args.output, ".vercel/output/config.json")),
  );
  assert.equal(config.routes[1].dest, "https://drone-api.onesa.eu/api/$1");
  const project = JSON.parse(
    await readFile(join(args.output, ".vercel/project.json")),
  );
  assert.equal(project.projectId, args.projectId);
});
