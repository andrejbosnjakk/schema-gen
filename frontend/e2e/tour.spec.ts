// The quickstart tour on a real `schemagen app` with a fresh home (tour_done false): it starts after the example opens, each
// step is finished by doing the real action, it can be skipped and replayed. Steps whose target is missing are skipped.
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startServer, type Server } from "./server";

test.describe.configure({ mode: "serial" });
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/screens/7-tour");
const pop = (p: Page) => p.locator(".driver-popover.sg-tour");
const count = (p: Page) => pop(p).locator(".sg-tour-count");
const title = (p: Page) => pop(p).locator(".driver-popover-title");

let srv: Server;
test.beforeAll(async () => { srv = await startServer(8830); });
test.afterAll(() => srv.stop());

const tourDone = async (page: Page) => (await (await page.request.get(srv.url + "api/session")).json()).tour_done as boolean;
const present = async (page: Page, name: string) => (await page.locator(`[data-tour=${name}]`).count()) > 0;
const inViewport = async (page: Page) => {
  const b = (await pop(page).boundingBox())!, v = page.viewportSize()!;
  expect(b.x).toBeGreaterThanOrEqual(0); expect(b.y).toBeGreaterThanOrEqual(0);
  expect(b.x + b.width).toBeLessThanOrEqual(v.width); expect(b.y + b.height).toBeLessThanOrEqual(v.height);
};

/** Does each step's real action and checks the next step shows. Returns the titles seen. */
async function walk(page: Page, shot?: (n: number) => Promise<void>) {
  const seen: string[] = [];
  const at = async (t: string) => { await expect(title(page)).toHaveText(t); await page.waitForTimeout(500); await inViewport(page); seen.push(t); };
  await at("Your whole system, one picture");
  if (shot) await shot(1);
  const d = (await page.locator("[data-tour=diagram]").boundingBox())!;
  await page.mouse.move(d.x + d.width / 2, d.y + d.height / 2);
  await page.mouse.wheel(0, -300);
  await at("Click a component");
  if (shot) await shot(2);
  await page.locator('[data-tour-node="CB-XPDR"]').click();
  await at("Everything about one part");
  await page.getByRole("button", { name: "Close" }).click();
  await at("What is wrong");
  if (shot) await shot(4);
  await page.locator(".issue:not([disabled])").first().click();
  await at("The sheet you know");
  // the drawer starts open: the step then asks for a click on a row, otherwise for opening it
  if (await page.locator("[data-tour=wires][aria-expanded=true]").count()) await page.locator("[role=row][data-id]").nth(1).click();
  else await page.locator("[data-tour=wires]").click();
  await at("Does it work with power on?");
  if (shot) await shot(6);
  await page.locator("[data-tour=simulate]").click();
  if (await present(page, "add-source")) { await at("Try a fix"); await page.locator("[data-tour=add-source]").click(); }
  await at("Now your own wiring");
  return seen;
}

test("starts after the example opens; each step advances on the real action; Done ends it for good", async ({ page }) => {
  await page.goto(srv.url);
  await page.getByRole("button", { name: "Open the example project" }).click();
  await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
  await expect(pop(page)).toBeVisible();
  const total = (await present(page, "add-source")) ? 8 : 7;
  await expect(count(page)).toHaveText(`1 of ${total}`);
  const seen = await walk(page);
  console.log(`tour steps shown: ${seen.length} of 8${total < 8 ? " (Try a fix skipped: no add-source target)" : ""}`);
  await expect(count(page)).toHaveText(`${total} of ${total}`);
  await pop(page).getByRole("button", { name: "Done" }).click();
  await expect(pop(page)).toHaveCount(0);
  await expect(page.locator(".driver-overlay")).toHaveCount(0);
  await expect.poll(() => tourDone(page)).toBe(true);
});

test("Next moves on without the action, a card never opened is skipped, Skip ends it, no tour on reload", async ({ page }) => {
  await page.goto(srv.url);
  await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
  await expect(pop(page)).toHaveCount(0);
  await page.getByRole("button", { name: "Help" }).click();
  await page.getByRole("menuitem", { name: "Replay the tour" }).click();
  await expect(title(page)).toHaveText("Your whole system, one picture");
  await pop(page).getByRole("button", { name: "Next" }).click();
  await expect(title(page)).toHaveText("Click a component");
  await pop(page).getByRole("button", { name: "Next" }).click();
  await expect(title(page)).toHaveText("What is wrong");
  await pop(page).getByRole("button", { name: "Skip tour" }).click();
  await expect(pop(page)).toHaveCount(0);
  await expect(page.locator(".driver-overlay")).toHaveCount(0);
});

test("replay from the help menu runs the whole tour again", async ({ page }) => {
  await page.goto(srv.url);
  await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Help" }).click();
  await page.getByRole("menuitem", { name: "Replay the tour" }).click();
  await walk(page);
  await pop(page).getByRole("button", { name: "Done" }).click();
  await expect(pop(page)).toHaveCount(0);
});

for (const [w, h] of [[1366, 768], [1920, 1080]]) for (const theme of ["light", "dark"]) {
  test(`screenshots ${w}x${h} ${theme}`, async ({ page }) => {
    fs.mkdirSync(OUT, { recursive: true });
    await page.setViewportSize({ width: w, height: h });
    await page.request.post(srv.url + "api/settings", { data: { theme } });
    await page.goto(srv.url);
    await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Help" }).click();
    await page.getByRole("menuitem", { name: "Replay the tour" }).click();
    const names: Record<number, string> = { 1: "1-diagram", 2: "2-component", 4: "4-issues", 6: "6-simulate" };
    await walk(page, async (n) => { await page.mouse.move(5, h - 5); await page.waitForTimeout(400); await page.screenshot({ path: path.join(OUT, `${names[n]}-${w}-${theme}.png`) }); });
    await pop(page).getByRole("button", { name: "Done" }).click();
  });
}
