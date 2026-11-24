import assert from "node:assert/strict";
import { test } from "node:test";
import {
  clearRequestedView,
  rememberRequestedView,
  requestedView,
  showProductOverview,
} from "../src/productEntry.ts";

test("a public feature returns through the account flow without enabling administrator views", (t) => {
  const descriptors = Object.getOwnPropertyDescriptors(globalThis);
  const fakeStorage = new Map();
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    value: {
      getItem: key => fakeStorage.get(key) ?? null,
      setItem: (key, value) => fakeStorage.set(key, value),
      removeItem: key => fakeStorage.delete(key),
    },
  });
  let current = new URL("https://drone.onesa.eu/");
  Object.defineProperty(globalThis, "location", { configurable: true, get: () => current });
  t.after(() => {
    for (const name of ["location", "sessionStorage"]) {
      if (descriptors[name]) Object.defineProperty(globalThis, name, descriptors[name]);
      else delete globalThis[name];
    }
  });
  assert.equal(showProductOverview(), true);

  current = new URL("/console?view=route", current);
  assert.equal(showProductOverview(), false);
  assert.equal(requestedView(), "Route planning");
  rememberRequestedView(requestedView());

  current = new URL("/?registration=complete", current);
  assert.equal(showProductOverview(), false);
  assert.equal(requestedView(), "Route planning");
  current = new URL("/", current);
  assert.equal(showProductOverview(), false);
  assert.equal(requestedView(), "Route planning");
  clearRequestedView();
  assert.equal(showProductOverview(), true);

  current = new URL("/console?view=Administration", current);
  assert.equal(requestedView(), "Dashboard");
});
