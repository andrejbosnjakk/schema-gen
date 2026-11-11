// Screenshots of steps 4 to 6 from a real `schemagen app`: docs/screens/4-card, 5-simulate, 6-source (1366x768 and 1920x1080, light and dark).
import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startServer } from "./server";

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/screens");
let port = 8850;
for (const [w, h] of [[1366, 768], [1920, 1080]]) for (const theme of ["light", "dark"]) {
  test(`screens 4-6 ${w}x${h} ${theme}`, async ({ page }) => {
    const srv = await startServer(port++);
    try {
      await page.setViewportSize({ width: w, height: h });
      const shot = (d: string, s: string) => page.screenshot({ path: path.join(OUT, d, `${w}-${theme}${s}.png`) });
      const node = (id: string) => page.locator(`.node-card[data-tour-node="${id}"]`);
      await page.request.post(srv.url + "api/settings", { data: { theme, tour_done: true } });
      await page.goto(srv.url);
      await page.getByRole("button", { name: "Open the example project" }).click();
      await expect(node("CB-XPDR")).toBeVisible({ timeout: 20_000 });
      await page.mouse.move(150, 520);
      await page.waitForTimeout(1200);

      await node("CB-XPDR").click();
      await expect(page.locator(".dialog .pin").first()).toBeVisible();
      await page.waitForTimeout(500);
      await shot("4-card", "-component");
      await page.keyboard.press("Escape");
      await page.getByLabel("Filter wires").fill("W045");
      await page.locator("[role=row][data-id=W045]").click();
      await expect(page.getByRole("dialog").getByLabel("Gauge")).toBeVisible();
      await page.waitForTimeout(500);
      await shot("4-card", "-wire");
      await page.keyboard.press("Escape");
      await page.getByLabel("Filter wires").fill("");
      await page.locator("[data-tour=fit]").click();
      await page.mouse.move(150, 520);
      await page.waitForTimeout(900);

      await page.locator("[data-tour=simulate]").click();
      await expect(page.getByRole("region", { name: "Simulation results" })).toBeVisible({ timeout: 30_000 });
      await page.mouse.move(150, 520);
      await page.waitForTimeout(1500);
      await shot("5-simulate", "");

      await page.locator("[data-tour=add-source]").click();
      await page.waitForTimeout(300);
      await shot("6-source", "-pick");
      await node("BB-CABIN-BUS").click();
      await expect(page.getByRole("dialog").getByLabel("Type")).toBeVisible();
      await page.waitForTimeout(500);
      await shot("6-source", "-dialog");
      await page.getByRole("dialog").getByRole("button", { name: "Add source" }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await page.mouse.move(150, 520);
      await page.waitForTimeout(800);
      await shot("6-source", "-added");
      await page.locator("[data-tour=simulate]").click();
      await expect(page.getByRole("region", { name: "Simulation results" })).not.toContainText("out of date", { timeout: 30_000 });
      await page.waitForTimeout(1000);
      await shot("6-source", "-simulated");
    } finally { srv.stop(); }
  });
}
