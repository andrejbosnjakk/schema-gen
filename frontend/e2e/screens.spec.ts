// Screenshots of steps 1 to 3 from a real `schemagen app`, at two sizes in both themes:
// docs/screens/1-start, 2-import (progress and drop overlay), 3-main. Each test starts its own server (fresh home, no project).
import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PYTHON, ROOT, serverEnv, startServer } from "./server";

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/screens");
const SIZES = [[1366, 768], [1920, 1080]];
const day = (n: number) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 19);
const RECENT = [{ name: "Kestrel E2 harness", opened: day(0) }, { name: "Example aircraft", opened: day(3) }];
const BASE = path.join(path.parse(os.tmpdir()).root, "schemagen", "projects");  // a short, neutral path for the Recent list
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sg-shots-"));
test.beforeAll(() => { execFileSync(PYTHON, ["-m", "schemagen", "synth", "--readable", "--wires", "300", "-o", dir], { env: serverEnv(dir), cwd: ROOT }); });

let port = 8810;
for (const [w, h] of SIZES) for (const theme of ["light", "dark"]) {
  test(`screens ${w}x${h} ${theme}`, async ({ page }) => {
    const srv = await startServer(port++, RECENT, BASE);
    try {
      await page.setViewportSize({ width: w, height: h });
      const shot = (d: string, suffix = "") => page.screenshot({ path: path.join(OUT, d, `${w}-${theme}${suffix}.png`) });
      await page.request.post(srv.url + "api/settings", { data: { theme } });
      await page.goto(srv.url);
      await expect(page.getByRole("button", { name: "Open the example project" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Recent" })).toBeVisible();
      await page.waitForTimeout(400);
      await shot("1-start");

      await page.getByRole("button", { name: "Open the example project" }).click();
      await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
      await page.mouse.move(150, 520);  // off the diagram, so no card is hovered
      await page.waitForTimeout(1200);  // fitView and the drawer settle
      await shot("3-main");

      // the drop overlay: a sheet dragged over the window
      await page.evaluate(() => {
        const dt = new DataTransfer(); dt.items.add(new File(["x"], "wires.xlsx"));
        window.dispatchEvent(new DragEvent("dragenter", { dataTransfer: dt, bubbles: true }));
      });
      await expect(page.getByText("Drop to import the wire sheet")).toBeVisible();
      await page.waitForTimeout(300);
      await shot("2-import", "-drop");
      await page.evaluate(() => {
        const dt = new DataTransfer(); dt.items.add(new File(["x"], "wires.xlsx"));
        window.dispatchEvent(new DragEvent("dragleave", { dataTransfer: dt, bubbles: true }));
      });

      // the import in progress: the real upload, held back for a moment so the bar can be seen
      await page.route("**/api/import", async (r) => { await new Promise((x) => setTimeout(x, 1800)); await r.continue(); });
      await page.locator("input[type=file]").setInputFiles(path.join(dir, "wires.xlsx"));
      await expect(page.locator(".importbar")).toBeVisible();
      await page.waitForTimeout(500);
      await shot("2-import");
      await expect(page.locator(".importbar")).toHaveCount(0, { timeout: 30_000 });
      await expect(page.locator(".issue").first()).toBeVisible();
      await page.waitForTimeout(1200);
      await shot("2-import", "-done");
    } finally { srv.stop(); }
  });
}
