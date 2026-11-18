import { test } from "node:test";
import assert from "node:assert/strict";
import { accountHome, enrollmentUrl, isEnrollmentReturn, registeredReturn } from "../src/account-navigation.mjs";

test("native user and admin registration use the reviewed Account origin and product", () => {
  assert.equal(accountHome, "https://account.onesa.eu/account");
  for (const platform of ["ios", "android"]) {
    for (const tier of ["user", "admin"]) {
      const url = new URL(enrollmentUrl(tier, platform));
      assert.equal(url.origin, "https://account.onesa.eu");
      assert.equal(url.pathname, "/register");
      assert.equal(url.searchParams.get("audience"), tier);
      assert.equal(url.searchParams.get("product"), "drone");
      assert.equal(url.searchParams.get("platform"), platform);
      assert.equal([...url.searchParams.keys()].length, 3);
    }
  }
});

test("native enrollment rejects unsupported roles and platforms", () => {
  for (const [tier, platform] of [["administrator", "ios"], ["viewer", "android"], ["admin", "web"], ["user", "unknown"], ["", "ios"]]) {
    assert.throws(() => enrollmentUrl(tier, platform), RangeError);
  }
});

test("only the fixed registration return is accepted; it is never a session grant", () => {
  assert.equal(registeredReturn, "onesadrone://account/registered");
  assert.equal(isEnrollmentReturn(registeredReturn), true);
  for (const value of [
    "onesadrone://account/registered?role=admin",
    "onesadrone://account/registered?code=token",
    "onesadrone://account/callback",
    "https://account.onesa.eu/registered",
    "onesadrone://account/registered#token",
    "",
    null,
  ]) assert.equal(isEnrollmentReturn(value), false);
});
