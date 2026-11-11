// Smoke test against an already running `schemagen app` (the installed wheel in CI): SMOKE_URL=http://127.0.0.1:8765/
import { test, expect } from "@playwright/test";

const URL = process.env.SMOKE_URL || "http://127.0.0.1:8765/";

test("installed app serves the bundled frontend and the open project", async ({ page }) => {
  await page.goto(URL);
  await expect(page.locator("[data-tour=diagram] .card").first()).toBeVisible();
  await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
  await expect(page.getByRole("complementary", { name: /Issues/ })).toBeVisible();
});
