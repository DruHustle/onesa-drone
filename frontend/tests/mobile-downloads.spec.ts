import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { storeListing } from "../src/mobile-store-listing.ts";

test("platform download links follow the verified website configuration", async ({ page }) => {
  const configured = JSON.parse(readFileSync(new URL("../src/mobile-downloads.json", import.meta.url), "utf8"));
  await page.goto("/");
  const section = page.getByRole("region", { name: "Onesa Drone mobile downloads" });
  await expect(section).toBeVisible();
  for (const platform of ["ios", "android"] as const) {
    const label = platform === "ios" ? "iOS" : "Android";
    const link = section.getByRole("link", { name: "Download Onesa Drone for " + label });
    const href = storeListing(platform, configured[platform]);
    if (href) {
      await expect(link).toHaveAttribute("href", href);
    } else {
      await expect(section.getByText(label + " · Unavailable")).toBeVisible();
      await expect(link).toHaveCount(0);
    }
  }
});

test("official listings are allowed independently for each platform", () => {
  const android = "https://play.google.com/store/apps/details?id=eu.onesa.drone";
  const ios = "https://apps.apple.com/gb/app/fixture/id1234567890";
  expect(storeListing("ios", ios)).toBe(ios);
  expect(storeListing("android", android)).toBe(android);
  expect(storeListing("ios", android)).toBeNull();
  expect(storeListing("android", ios)).toBeNull();
  expect(storeListing("ios", null)).toBeNull();
  expect(storeListing("android", null)).toBeNull();
  expect(storeListing("ios", ios.replace("apps.apple.com", "example.test"))).toBeNull();
  expect(storeListing("android", android.replace("eu.onesa.drone", "another.app"))).toBeNull();
});
