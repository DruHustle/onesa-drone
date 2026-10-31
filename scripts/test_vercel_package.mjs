import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  access,
  cp,
  mkdtemp,
  mkdir,
  writeFile,
  readFile,
  rm,
  symlink,
  truncate,
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
  await mkdir(join(dist, "models"), { recursive: true });
  await cp(new URL("../frontend/public/models/nvidia", import.meta.url),
    join(dist, "models/nvidia"), { recursive: true });
  await mkdir(join(dist, "licenses"), { recursive: true });
  await cp(new URL("../frontend/public/licenses/three.txt", import.meta.url),
    join(dist, "licenses/three.txt"));
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
  assert.equal(Object.keys(result.files).length, 16);
  const catalogBytes = await readFile(new URL("../frontend/src/nvidia-manifest.json", import.meta.url));
  const expected = new Map([["models/nvidia/manifest.json", catalogBytes]]);
  for (const asset of JSON.parse(catalogBytes).assets) {
    for (const key of ["glb", "thumbnail", "licenseFile", "sourceFile"]) {
      const file = asset[key];
      const path = "models/nvidia/" + file.path;
      const delivered = await readFile(join(args.output, ".vercel/output/static", path));
      assert.equal(delivered.length, file.byteLength);
      assert.equal(createHash("sha256").update(delivered).digest("hex"), file.sha256);
      assert.equal(result.files[path], file.sha256);
    }
  }
  expected.set("licenses/three.txt",
    await readFile(new URL("../frontend/public/licenses/three.txt", import.meta.url)));
  for (const [path, bytes] of expected) {
    assert.deepEqual(await readFile(join(args.output, ".vercel/output/static", path)), bytes);
    assert.equal(result.files[path], createHash("sha256").update(bytes).digest("hex"));
  }
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

test("arbitrary JSON, GLB and unlisted NVIDIA files are refused before output", async (t) => {
  const { args } = await fixture(t);
  for (const path of [
    "assets/private.json", "assets/unreviewed.glb",
    "models/nvidia/private.json", "models/nvidia/private.png",
  ]) {
    const file = join(args.dist, path);
    await writeFile(file, "synthetic-unreviewed-fixture");
    await assert.rejects(packageVercel(args), /Unexpected or oversized/);
    await assert.rejects(access(args.output), { code: "ENOENT" });
    await rm(file);
  }
});

test("every catalogued reference and the renderer notice is required before output", async (t) => {
  const { args } = await fixture(t);
  const catalog = JSON.parse(await readFile(join(args.dist, "models/nvidia/manifest.json")));
  const paths = ["models/nvidia/manifest.json", "licenses/three.txt"];
  for (const asset of catalog.assets)
    for (const key of ["glb", "thumbnail", "licenseFile", "sourceFile"])
      paths.push("models/nvidia/" + asset[key].path);
  for (const path of paths) {
    const file = join(args.dist, path);
    const original = await readFile(file);
    await rm(file);
    await assert.rejects(packageVercel(args), /Required pinned public artifacts/);
    await assert.rejects(access(args.output), { code: "ENOENT" });
    await writeFile(file, original);
  }
});

test("changed pinned model, preview, provenance, licenses and catalog bytes are refused", async (t) => {
  const { args } = await fixture(t);
  const catalog = JSON.parse(await readFile(join(args.dist, "models/nvidia/manifest.json")));
  const paths = ["models/nvidia/manifest.json", "licenses/three.txt"];
  for (const key of ["glb", "thumbnail", "licenseFile", "sourceFile"])
    paths.push("models/nvidia/" + catalog.assets[0][key].path);
  for (const path of paths) {
    const file = join(args.dist, path);
    const original = await readFile(file);
    const changed = Buffer.from(original);
    changed[0] ^= 1; // Preserve length so the content hash must catch the change.
    await writeFile(file, changed);
    await assert.rejects(packageVercel(args), /Pinned public artifact integrity mismatch/);
    await assert.rejects(access(args.output), { code: "ENOENT" });
    await writeFile(file, original);
  }
});

test("the existing per-file size bound still rejects otherwise supported artifacts", async (t) => {
  const { args } = await fixture(t);
  const file = join(args.dist, "assets/oversized.js");
  await writeFile(file, "");
  await truncate(file, 10 * 1024 * 1024 + 1);
  await assert.rejects(packageVercel(args), /Unexpected or oversized/);
  await assert.rejects(access(args.output), { code: "ENOENT" });
});
