import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const project = JSON.parse(await readFile(new URL("package.json", root)));
const lock = JSON.parse(await readFile(new URL("package-lock.json", root)));
// The monorepo compatibility build installs web dependencies at frontend/node_modules;
// a standalone web installation keeps them inside drone/web/node_modules.
let installedFile = new URL("node_modules/three/package.json", root);
let licenseFile = new URL("node_modules/three/LICENSE", root);
try {
  await readFile(installedFile);
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
  installedFile = new URL("../../node_modules/three/package.json", root);
  licenseFile = new URL("../../node_modules/three/LICENSE", root);
}
const installed = JSON.parse(await readFile(installedFile));
const entry = lock.packages["node_modules/three"];
assert.match(project.dependencies.three, /^\d+\.\d+\.\d+$/);
assert.equal(entry.version, project.dependencies.three);
assert.equal(installed.version, project.dependencies.three);
assert.equal(installed.license, "MIT");
assert.equal(entry.resolved, "https://registry.npmjs.org/three/-/three-" + entry.version + ".tgz");
assert.match(entry.integrity, /^sha512-/);
assert.deepEqual(
  await readFile(new URL("public/licenses/three.txt", root)),
  await readFile(licenseFile),
  "The browser distribution must retain the exact installed Three.js MIT notice",
);
console.log("Pinned Three.js version, registry integrity and browser license notice verified.");
