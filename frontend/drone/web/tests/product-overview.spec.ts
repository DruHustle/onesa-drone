import { expect, test } from "@playwright/test";

test("anonymous visitors can explore synthetic examples without an API", async ({ page }) => {
  const requests: string[] = [];
  await page.route("**/api/**", route => {
    requests.push(new URL(route.request().url()).pathname);
    return route.abort();
  });
  await page.goto("/explore");
  await expect(page.getByRole("heading", { name: "Onesa Drone", exact: true })).toBeVisible();
  await page.getByText("Synthetic example", { exact: true }).first().click();
  await expect(page.getByText(/Demo aircraft D-14/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Create an Onesa account" })).toHaveAttribute(
    "href", "https://account.onesa.eu/register?product=drone&platform=web&audience=user",
  );
  expect(requests).toEqual([]);
  await page.unroute("**/api/**");
  await page.getByRole("link", { name: "Open Fleet" }).click();
  await expect(page).toHaveURL(/\/console\?view=fleet$/);
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
});
