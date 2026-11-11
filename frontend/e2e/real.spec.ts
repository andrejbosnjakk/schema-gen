// The main screen against a real `schemagen app` (see playwright.config.ts). The server keeps its open project between
// tests, so these run in order: start screen, example, imports.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { PYTHON, ROOT, serverEnv } from "./server";

test.describe.configure({ mode: "serial" });

const noSideScroll = (p: Page, sel: string) => p.evaluate((s) => { const e = document.querySelector(s)!; return e.scrollWidth <= e.clientWidth; }, sel);
/** The React Flow viewport's zoom, read from its transform. */
export const zoomOf = (p: Page) => p.evaluate(() => new DOMMatrix(getComputedStyle(document.querySelector(".react-flow__viewport")!).transform).a);
const cardFontPx = (p: Page) => p.evaluate(() => parseFloat(getComputedStyle(document.querySelector(".card-name")!).fontSize) * (new DOMMatrix(getComputedStyle(document.querySelector(".react-flow__viewport")!).transform).a));

test("start screen: no project yet, one primary button, no sideways scroll", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Open the example project" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Import your wire sheet/ })).toBeVisible();
  expect(await noSideScroll(page, "html")).toBe(true);
});

test("open the example: diagram, issues and wires; readable at fit-to-screen", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open the example project" }).click();
  await expect(page.locator("[data-tour=diagram] .node-card").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".issue").first()).toBeVisible();
  await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
  await page.waitForTimeout(600);  // fitView settles
  const z = await zoomOf(page);
  console.log(`real example fit zoom at 1366x768: ${z.toFixed(2)}, card name ${(await cardFontPx(page)).toFixed(1)} px`);
  expect(z).toBeGreaterThanOrEqual(0.8);
  expect(await cardFontPx(page)).toBeGreaterThanOrEqual(11);
  for (const sel of ["html", ".tbody", ".issues-body", ".topbar"]) expect(await noSideScroll(page, sel), sel).toBe(true);
  expect(await page.locator(".tr.th > [role=columnheader]").count()).toBeLessThanOrEqual(7);
  const h = (await page.locator(".wires").boundingBox())!.height;
  expect(h).toBeLessThanOrEqual(768 * 0.28);
  expect(await page.locator("[role=row][data-id]").count()).toBeGreaterThanOrEqual(3);
});

test("a reload opens the project again; wire row click and issue click work on real data", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
  await page.locator("[role=row][data-id]").nth(2).click();
  await page.keyboard.press("Escape");  // the row opens the wire card
  await expect(page.locator(".node-card.hl")).toHaveCount(2);
  await page.locator(".issue:not([disabled])").first().click();
  await expect(page.locator(".node-card.anim-pulse").first()).toBeVisible();
});

test("axe on the real main screen, light and dark", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
  for (const t of ["light", "dark"]) {
    await page.evaluate((x) => { document.documentElement.dataset.theme = x; }, t);
    await page.waitForTimeout(500);
    const r = await new AxeBuilder({ page }).analyze();
    expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical"), t).toEqual([]);
  }
});

test.describe("import", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sg-sheet-"));
  const csv = path.join(dir, "wires.xlsx");  // synth writes a project folder; the sheet is the import
  test.beforeAll(() => { execFileSync(PYTHON, ["-m", "schemagen", "synth", "--readable", "--wires", "300", "-o", dir], { env: serverEnv(dir), cwd: ROOT }); });

  test("a readable sheet from synth: diagram, issues, wires, no sideways scroll", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
    await page.locator("input[type=file]").setInputFiles(csv);
    await expect(page.locator(".importbar")).toHaveCount(0, { timeout: 30_000 });
    await expect(page.locator(".node-card").first()).toBeVisible();
    await expect(page.locator(".issue").first()).toBeVisible();
    await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
    for (const sel of ["html", ".tbody", ".issues-body"]) expect(await noSideScroll(page, sel), sel).toBe(true);
    await expect(page.locator(".toast.err")).toHaveCount(0);
  });

  test("the example workbook imports", async ({ page }) => {
    await page.goto("/");
    await page.locator("input[type=file]").setInputFiles(path.join(ROOT, "examples", "aircraft", "wires.xlsx"));
    await expect(page.locator(".importbar")).toHaveCount(0, { timeout: 30_000 });
    await expect(page.locator(".node-card").first()).toBeVisible();
    await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
    await expect(page.locator(".toast.err")).toHaveCount(0);
  });

  test("a file that is not a sheet gives a plain message, never a raw error", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
    await page.locator("input[type=file]").setInputFiles({ name: "broken.xlsx", mimeType: "application/octet-stream", buffer: Buffer.from("this is not a workbook") });
    const toast = page.locator(".toast.err");
    await expect(toast).toBeVisible({ timeout: 20_000 });
    await expect(toast).not.toContainText(/\b(400|404|422|500)\b|Failed to fetch|Traceback|detail/i);
    console.log("bad import message:", await toast.innerText());
  });
});

test("a bad request shows a plain message with Retry", async ({ page }) => {
  await page.route("**/api/open", (r) => r.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error" }));
  await page.goto("/");
  await page.getByRole("button", { name: /Open the example project|Import your wire sheet/ }).first().isVisible().catch(() => false);
  // the project is open on the server by now; reach the start screen through a session without one
  await page.route("**/api/session", async (r) => { const j = await (await r.fetch()).json(); await r.fulfill({ json: { ...j, project: null } }); });
  await page.reload();
  await page.getByRole("button", { name: "Open the example project" }).click();
  const toast = page.locator(".toast.err");
  await expect(toast).toBeVisible();
  await expect(toast).not.toContainText(/500|Failed to fetch|Internal Server Error/);
  await expect(toast.getByRole("button", { name: "Retry" })).toBeVisible();
});
