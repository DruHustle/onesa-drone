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
