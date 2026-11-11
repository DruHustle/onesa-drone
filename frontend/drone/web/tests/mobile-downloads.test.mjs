import assert from "node:assert/strict";
import { test } from "node:test";
import { storeListing } from "../src/mobile-store-listing.ts";

test("each platform links only to a configured official listing", () => {
  const android = "https://play.google.com/store/apps/details?id=eu.onesa.drone";
  const ios = "https://apps.apple.com/gb/app/fixture/id1234567890";
  assert.equal(storeListing("ios", ios), ios);
  assert.equal(storeListing("android", android), android);
  for (const platform of ["ios", "android"]) {
    for (const value of [null, "", false, "https://example.test/file.apk", "javascript:void(0)"]) {
      assert.equal(storeListing(platform, value), null);
    }
  }
  assert.equal(storeListing("android", ios), null);
  assert.equal(storeListing("ios", android), null);
  assert.equal(storeListing("android", android.replace("eu.onesa.drone", "another.app")), null);
  assert.equal(storeListing("android", android + "&referrer=demo"), null);
  assert.equal(storeListing("ios", ios.replace("apps.apple.com", "apps.apple.com.example.test")), null);
  assert.equal(storeListing("ios", ios.replace("https://", "https://fixture@")), null);
});

test("verified first-party APKs and public TestFlight invitations can be installed from the website", () => {
  const beta = "https://testflight.apple.com/join/Ab12Cd34";
  assert.equal(storeListing("ios", beta), beta);
  assert.equal(storeListing("ios", beta + "?redirect=other"), null);
  assert.equal(storeListing("android", beta), null);
  const github = "https://github.com/DruHustle/onesa-drone/releases/download/mobile-v0.1.0/onesa-drone-android-v0.1.0.apk";
  const product = "https://drone.onesa.eu/downloads/onesa-drone-android-v0.1.0.apk";
  const hashes = { sha256: "a".repeat(64), certificateSha256: "b".repeat(64), sourceCommit: "c".repeat(40) };
  for (const url of [github, product]) {
    assert.equal(storeListing("android", { url, ...hashes }), url);
    assert.equal(storeListing("android", url), null);
    assert.equal(storeListing("ios", { url, ...hashes }), null);
    assert.equal(storeListing("android", { url, ...hashes, certificateSha256: "" }), null);
  }
  for (const url of [github.replace("DruHustle", "another-owner"), github.replace("mobile-v0.1.0", "mobile-v0.2.0"),
    github.replace("/releases/download/", "/actions/runs/"), product.replace(".apk", "-debug.apk"),
    product.replace("drone.onesa.eu","untrusted.example"), github + "?download=1"]) {
    assert.equal(storeListing("android", { url, ...hashes }), null);
  }
});
