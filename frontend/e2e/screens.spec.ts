// Screenshots of steps 1 to 3 at two sizes in both themes: docs/screens/1-start, 2-import, 3-main.
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/screens");
const SIZES = [[1366, 768], [1920, 1080]];
const csv = "label,name,from,to,gauge,voltage,current\n" + Array.from({ length: 300 }, (_, i) => `W${i},w,A,B,20,14 V,1`).join("\n");

for (const [w, h] of SIZES) for (const theme of ["light", "dark"]) {
  test(`screens ${w}x${h} ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    const set = () => page.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
    const shot = (dir: string) => page.screenshot({ path: path.join(OUT, dir, `${w}-${theme}.png`) });
    await page.goto("/?mock=1&slow=1");
    await expect(page.getByRole("button", { name: "Open the example project" })).toBeVisible(); await set();
    await page.waitForTimeout(250);
    await shot("1-start");
    await page.getByRole("button", { name: "Open the example project" }).click();
    await expect(page.locator(".node-card").first()).toBeVisible(); await set();
    // import: the progress bar over the diagram being replaced
    await page.locator("input[type=file]").setInputFiles({ name: "wire-sheet.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
    await expect(page.locator(".importbar")).toBeVisible();
    await page.waitForTimeout(350);
    await shot("2-import");
    await expect(page.locator(".issue", { hasText: "pin cell" })).toBeVisible();
    await page.goto("/?mock=1&open=1");
    await expect(page.locator(".node-card").first()).toBeVisible(); await set();
    await page.waitForTimeout(900);
    await shot("3-main");
  });
}
