import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readdir, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, relative, sep } from "node:path";
import { packageVercel } from "./vercel_package.mjs";

// A local regression artifact with synthetic project metadata confers no hosted
// qualification. Exercise the real packager and actual fresh production output.
const dist = resolve("frontend/dist");
const root = await mkdtemp(join(tmpdir(), "onesa-drone-built-package-"));
const output = join(root, "release");
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
try {
  const result = await packageVercel({
    dist, output, environment: "staging",
    backendOrigin: "https://drone-api-staging.onesa.eu",
    sourceCommit: "a".repeat(40),
    projectId: "prj_SyntheticBuiltArtifact",
    orgId: "team_synthetic_fixture",
  });
  const delivered = join(output, ".vercel/output/static");
  const files = [];
  async function collect(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) await collect(path);
      else files.push(relative(dist, path).split(sep).join("/"));
    }
  }
  await collect(dist);
  assert.deepEqual(Object.keys(result.files).sort(), files.sort());
  let byteCount = 0;
  for (const path of files) {
    const built = await readFile(join(dist, path));
    const packaged = await readFile(join(delivered, path));
    byteCount += built.length;
    assert.deepEqual(packaged, built, "Packaged bytes differ: " + path);
    assert.equal(result.files[path], hash(packaged));
  }
  assert.equal(result.bytes, byteCount);
  assert.deepEqual(JSON.parse(await readFile(join(output, "release.json"))), result);
  const catalogBytes = await readFile("frontend/src/nvidia-manifest.json");
  assert.deepEqual(await readFile(join(delivered, "models/nvidia/manifest.json")), catalogBytes);
  const catalog = JSON.parse(catalogBytes);
  let references = 0;
  for (const asset of catalog.assets) {
    for (const key of ["glb", "thumbnail", "licenseFile", "sourceFile"]) {
      const expected = asset[key];
      const path = "models/nvidia/" + expected.path;
      const bytes = await readFile(join(delivered, path));
      assert.equal(bytes.length, expected.byteLength);
      assert.equal(hash(bytes), expected.sha256);
      assert.equal(result.files[path], expected.sha256);
      references++;
    }
  }
  assert.equal(references, 12);
  assert.deepEqual(
    await readFile(join(delivered, "licenses/three.txt")),
    await readFile("frontend/node_modules/three/LICENSE"),
  );
  console.log(JSON.stringify({
    evidence: "local-built-output-packaging-regression",
    files: files.length, bytes: byteCount, pinnedNvidiaFiles: references + 1,
    rendererNotice: "exact installed Three.js MIT bytes",
  }));
} finally {
  await rm(root, { recursive: true, force: true });
}
