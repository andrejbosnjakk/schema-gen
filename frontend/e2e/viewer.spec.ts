// The wiring diagram viewer and the shift-click selection on the map, against the in-memory mock (src/mock). SHOTS=<dir> also writes screenshots.
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const shot = async (p: Page, name: string) => { const d = process.env.SHOTS; if (d) { fs.mkdirSync(d, { recursive: true }); await p.screenshot({ path: path.join(d, `${name}.png`) }); } };
const node = (p: Page, id: string) => p.locator(`.node-card[data-tour-node="${id}"]`);
const open = async (p: Page) => { await p.goto("/?mock=1&open=1"); await expect(node(p, "CB-XPDR")).toBeVisible(); await p.waitForTimeout(900); };
const pickTwo = async (p: Page) => { await node(p, "CB-XPDR").click({ modifiers: ["Shift"] }); await node(p, "CB-GPS").click({ modifiers: ["Shift"] }); };
const viewer = (p: Page) => p.getByRole("dialog");

test("shift-click two components: selected look, the bar, the viewer opens with a sheet", async ({ page }) => {
  await open(page);
  await pickTwo(page);
  await expect(page.getByRole("dialog")).toHaveCount(0);                       // a shift-click opens no card
  await expect(node(page, "CB-XPDR")).toHaveClass(/\bsel\b/);
  await expect(node(page, "CB-GPS")).toHaveClass(/\bsel\b/);
  const bar = page.locator(".sel-bar");
  await expect(bar).toContainText("2 components selected");
  await shot(page, "map-selection-bar");
  await node(page, "CB-XPDR").click({ modifiers: ["Shift"] });                // toggles off
  await expect(bar).toContainText("1 component selected");
  await node(page, "CB-XPDR").click({ modifiers: ["Shift"] });
  await bar.getByRole("button", { name: "Wiring diagram" }).click();
  await expect(viewer(page).locator(".vw-paper svg")).toBeVisible();
  await expect(viewer(page).getByRole("heading", { level: 2 })).toHaveText("Selection");
  await expect(viewer(page).getByRole("status")).toHaveText("Sheet 1 of 2");
  const white = await viewer(page).locator(".vw-paper").evaluate((e) => getComputedStyle(e).backgroundColor);
  expect(white).toBe("rgb(255, 255, 255)");
  await shot(page, "viewer-selection");
});

test("a plain click still opens the card, and Clear empties the selection", async ({ page }) => {
  await open(page);
  await node(page, "CB-GPS").click({ modifiers: ["Shift"] });
  await node(page, "CB-XPDR").click();
  await expect(viewer(page)).toBeVisible();
  await expect(viewer(page).locator(".kind-chip")).toContainText("breaker");
  await page.keyboard.press("Escape");
  await expect(page.locator(".sel-bar")).toContainText("1 component selected");
  await page.locator(".sel-bar").getByRole("button", { name: "Clear" }).click();
  await expect(page.locator(".sel-bar")).toHaveCount(0);
  await expect(node(page, "CB-GPS")).not.toHaveClass(/\bsel\b/);
});

test("Escape clears the selection, so does a click on the empty map", async ({ page }) => {
  await open(page);
  await pickTwo(page);
  await expect(page.locator(".sel-bar")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".sel-bar")).toHaveCount(0);
  await pickTwo(page);
  await page.locator(".react-flow__pane").click({ position: { x: 5, y: 5 } });
  await expect(page.locator(".sel-bar")).toHaveCount(0);
});

test("a component card's Wiring diagram opens the viewer; next and previous sheet; Escape closes", async ({ page }) => {
  await open(page);
  await node(page, "CB-XPDR").click();
  const card = viewer(page);
  await expect(card.getByRole("button", { name: "Save as PDF" })).toHaveCount(0);
  await card.getByRole("button", { name: "Wiring diagram" }).click();
  await expect(card.getByRole("heading", { level: 2 })).toHaveText("CB-XPDR");
  await expect(card.locator(".vw-paper svg")).toBeVisible();
  const status = card.getByRole("status");
  await expect(status).toHaveText("Sheet 1 of 2");
  await expect(card.getByRole("button", { name: "Previous sheet" })).toBeDisabled();
  await card.getByRole("button", { name: "Next sheet" }).click();
  await expect(status).toHaveText("Sheet 2 of 2");
  await expect(card.locator(".vw-paper svg")).toContainText("Sheet 2 of 2");
  await expect(card.getByRole("button", { name: "Next sheet" })).toBeDisabled();
  await card.getByRole("button", { name: "Previous sheet" }).click();
  await expect(status).toHaveText("Sheet 1 of 2");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("in the viewer the wheel zooms, a drag pans, Fit resets; Save as PDF shows the toast", async ({ page }) => {
  await open(page);
  await node(page, "CB-XPDR").click();
  await page.getByRole("dialog").getByRole("button", { name: "Wiring diagram" }).click();
  const paper = page.locator(".vw-paper");
  await expect(paper.locator("svg")).toBeVisible();
  const t0 = await paper.evaluate((e) => (e as HTMLElement).style.transform);
  const b = (await page.locator(".vw-stage").boundingBox())!;
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.mouse.wheel(0, -400);
  await expect.poll(() => paper.evaluate((e) => (e as HTMLElement).style.transform)).not.toBe(t0);
  const t1 = await paper.evaluate((e) => (e as HTMLElement).style.transform);
  await page.mouse.down(); await page.mouse.move(b.x + b.width / 2 + 60, b.y + b.height / 2 + 30, { steps: 4 }); await page.mouse.up();
  await expect.poll(() => paper.evaluate((e) => (e as HTMLElement).style.transform)).not.toBe(t1);
  await page.getByRole("button", { name: "Fit", exact: true }).click();
  await expect.poll(() => paper.evaluate((e) => (e as HTMLElement).style.transform)).toBe(t0);
  await shot(page, "viewer-component");
  await page.getByRole("button", { name: "Save as PDF" }).click();
  await expect(page.locator(".toast.ok")).toContainText("Wiring diagram: 1 file saved.");
  await expect(page.locator(".toast.ok").getByRole("button", { name: "Show folder" })).toBeVisible();
  await expect(page.getByRole("dialog")).toBeVisible();                         // the viewer stays open
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("the viewer shows white paper in the dark theme too", async ({ page }) => {
  await open(page);
  await page.evaluate(() => { document.documentElement.dataset.theme = "dark"; });
  await pickTwo(page);
  await page.locator(".sel-bar").getByRole("button", { name: "Wiring diagram" }).click();
  await expect(page.locator(".vw-paper svg")).toBeVisible();
  expect(await page.locator(".vw-paper").evaluate((e) => getComputedStyle(e).backgroundColor)).toBe("rgb(255, 255, 255)");
  await page.keyboard.press("Escape");
});
