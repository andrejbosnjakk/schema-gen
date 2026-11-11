// The main screen against the in-memory mock server (src/mock). Built with `vite build --mode mock`.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const csv = (n: number) => "label,name,from,to,gauge,voltage,current\n" + Array.from({ length: n }, (_, i) =>
  `W${i + 1},Wire ${i + 1},A${i} 1,B${i} 1,20 AWG,14 V,1`).join("\n");
const sheet = (n: number) => ({ name: "sheet.csv", mimeType: "text/csv", buffer: Buffer.from(csv(n)) });
const noSideScroll = (p: Page, sel: string) =>
  p.evaluate((s) => { const e = document.querySelector(s)!; return e.scrollWidth <= e.clientWidth; }, sel);
const serious = (r: { violations: { impact?: string | null }[] }) => r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");

test("start screen: logo, example, drop zone, recent", async ({ page }) => {
  await page.goto("/?mock=1");
  await expect(page.getByRole("button", { name: "Open the example project" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Import your wire sheet/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent" })).toBeVisible();
  await expect(page.locator(".sg-logo").first()).toBeVisible();
  expect(await noSideScroll(page, "html")).toBe(true);
});

test("open the example: diagram, issues and wires appear together", async ({ page }) => {
  await page.goto("/?mock=1");
  await page.getByRole("button", { name: "Open the example project" }).click();
  await expect(page.locator("[data-tour=diagram] .node-card").first()).toBeVisible();
  await expect(page.getByRole("complementary", { name: /Issues/ })).toBeVisible();
  await expect(page.locator(".issue").first()).toBeVisible();
  await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
  await expect(page.locator(".topbar").getByText("Kestrel E2")).toBeVisible();
  for (const b of ["Import", "Export", "Simulate"]) await expect(page.locator(".topbar").getByRole("button", { name: b })).toBeVisible();
});

test("import a CSV through the file chooser; import problems go to Issues", async ({ page }) => {
  await page.goto("/?mock=1");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: /Import your wire sheet/ }).click();
  (await chooser).setFiles(sheet(60));
  await expect(page.locator("[data-tour=diagram] .node-card").first()).toBeVisible();
  await expect(page.locator(".issue", { hasText: "pin cell could not be read" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("import of 500 wires: diagram and issues within 3 s", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await expect(page.locator(".node-card").first()).toBeVisible();
  const t0 = Date.now();
  await page.locator("input[type=file]").setInputFiles(sheet(500));
  await expect(page.locator(".issue", { hasText: "pin cell could not be read" })).toBeVisible({ timeout: 3000 });
  await expect(page.locator(".node-card").first()).toBeVisible();
  expect(Date.now() - t0).toBeLessThan(3000);
});

test("a sheet dragged over the window shows the overlay", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await expect(page.locator(".node-card").first()).toBeVisible();
  await page.evaluate(() => {
    const dt = new DataTransfer(); dt.items.add(new File(["x"], "a.csv", { type: "text/csv" }));
    window.dispatchEvent(new DragEvent("dragenter", { dataTransfer: dt, bubbles: true }));
  });
  await expect(page.getByText("Drop to import the wire sheet")).toBeVisible();
});

test("no horizontal scroll at 1366 px: document, wires drawer, issues", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
  for (const sel of ["html", ".tbody", ".issues-body", ".topbar"]) expect(await noSideScroll(page, sel), sel).toBe(true);
  expect(await page.locator(".tr.th > [role=columnheader]").count()).toBeLessThanOrEqual(7);
});

test("an issue click zooms to the object and pulses it", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await expect(page.locator(".node-card").first()).toBeVisible();
  const before = await page.locator(".react-flow__viewport").getAttribute("style");
  await page.locator(".issue").first().click();
  await expect(page.locator(".node-card.anim-pulse").first()).toBeVisible();
  await expect.poll(() => page.locator(".react-flow__viewport").getAttribute("style")).not.toBe(before);
});

test("a wire row click highlights the edge and its two cards", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await page.locator("[role=row][data-id]").nth(3).click();
  await expect(page.locator(".node-card.hl")).toHaveCount(2);
  await expect(page.locator(".bundle.hl")).toHaveCount(1);
});

test("a component click opens a minimal dialog", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await page.locator(".node-card").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("theme toggle switches both ways", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await page.getByRole("button", { name: /Switch to dark theme/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: /Switch to light theme/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("a failed open shows a plain message with Retry, never a raw status", async ({ page }) => {
  await page.goto("/?mock=1&fail=open");
  await page.getByRole("button", { name: "Open the example project" }).click();
  const toast = page.locator(".toast.err");
  await expect(toast).toContainText("could not be opened");
  await expect(toast).not.toContainText(/500|Failed to fetch/);
  await toast.getByRole("button", { name: "Retry" }).click();
  await expect(page.locator(".node-card").first()).toBeVisible();
});

test("the wire filter narrows the list", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  const rows = page.locator("[role=row][data-id]");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(1);
  await page.getByLabel("Filter wires").fill("W045");
  await expect(rows).toHaveCount(1);
});

test("1,000 wires: the drawer toggles within a quarter second", async ({ page }) => {
  await page.goto("/?mock=1&open=1&wires=1000");
  await expect(page.locator(".node-card").first()).toBeVisible();
  const ms = await page.evaluate(async () => {
    const t = performance.now(); document.querySelector<HTMLButtonElement>(".drawer-handle")!.click();
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); return performance.now() - t;
  });
  expect(ms).toBeLessThan(250);
});

for (const theme of ["light", "dark"]) {
  test(`axe: no serious violations (${theme}, start and main)`, async ({ page }) => {
    await page.goto("/?mock=1");
    await page.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
    await page.waitForTimeout(500);  // let colour transitions finish
    expect(serious(await new AxeBuilder({ page }).analyze()), "start").toEqual([]);
    await page.getByRole("button", { name: "Open the example project" }).click();
    await expect(page.locator(".node-card").first()).toBeVisible();
    await page.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
    await page.waitForTimeout(500);  // let colour transitions finish
    expect(serious(await new AxeBuilder({ page }).analyze()), "main").toEqual([]);
  });
}
