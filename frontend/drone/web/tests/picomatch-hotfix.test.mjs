import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const picomatch = require("picomatch");

test("reviewed Onesa picomatch mitigates repeated-extglob ReDoS without breaking normal Vite globs", () => {
  assert.equal(require("picomatch/package.json").version, "4.0.8-onesa.1");
  for (const pattern of ["+(*)", "+(*a)", "+(a*)", "*(a*|b)", "+(ab|abab)"]) {
    assert.equal(picomatch.isMatch("a".repeat(150) + "!", pattern), false);
    assert.equal(picomatch.isMatch(pattern, pattern), true);
  }
  assert.equal(picomatch.isMatch("drone/web/src/flight.tsx", "drone/web/src/**/*.tsx"), true);
  assert.equal(picomatch.isMatch("drone/web/src/flight.js", "drone/web/src/**/*.tsx"), false);
  assert.equal(picomatch.isMatch("drone/web/.private/secret.tsx", "drone/web/**/*.tsx", { dot: true }), true);
  assert.equal(picomatch.isMatch("fff", "*(f)"), true);
});
