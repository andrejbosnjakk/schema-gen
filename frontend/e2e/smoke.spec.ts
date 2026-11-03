// Smoke test against an already running `schemagen app` (the installed wheel in CI): SMOKE_URL=http://127.0.0.1:8765/
import { test, expect } from "@playwright/test";

const URL = process.env.SMOKE_URL || "http://127.0.0.1:8765/";

test("installed app serves the bundled frontend and the demo project", async ({ page }) => {
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: /^Wires/ })).toBeVisible();
  await expect(page.locator("tr[data-id]")).toHaveCount(23);
  await page.locator('[data-pin="ECU/J1/2"]').first().click();
  await expect(page.getByRole("status").filter({ hasText: "highlighted" })).toBeVisible();
  await page.keyboard.press("Control+k");
  await page.getByRole("dialog", { name: "Search every object" }).getByRole("searchbox").fill("X-BH");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("X-BH");
});
