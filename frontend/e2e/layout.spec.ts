// No layout jumps (an added source keeps every card where it was, and stays next to its bus after a reload) and
// a collapsed Simulate summary never covers a card. Real server of its own, the example project.
import { expect, test, type Page } from "@playwright/test";
import { startServer, type Server } from "./server";

let srv: Server;
test.beforeAll(async () => { srv = await startServer(8870); });
test.afterAll(() => srv.stop());

const node = (p: Page, id: string) => p.locator(`.node-card[data-tour-node="${id}"]`);
const ready = async (p: Page) => { await p.goto(srv.url); await expect(p.locator(".node-card").first()).toBeVisible({ timeout: 20_000 }); await p.waitForTimeout(800); };
/** Every card's top-left in diagram coordinates (independent of pan and zoom). */
const flowPos = (p: Page) => p.evaluate(() => Object.fromEntries([...document.querySelectorAll<HTMLElement>(".react-flow__node-card")].map((e) => {
  const m = new DOMMatrix(getComputedStyle(e).transform); return [e.dataset.id!, [Math.round(m.e), Math.round(m.f)]]; })));

test.beforeEach(async ({ page }) => { await page.request.post(srv.url + "api/settings", { data: { tour_done: true } }); });

test("adding a source keeps every card where it was, also after a reload; the source stays beside its bus", async ({ page }) => {
  await page.goto(srv.url);
  await page.getByRole("button", { name: "Open the example project" }).click();
  await expect(page.locator(".node-card").first()).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(800);
  const before = await flowPos(page), ids = Object.keys(before);
  expect(ids.length).toBeGreaterThan(10);
  for (const id of ["CB-XPDR", "BB-CABIN-BUS"]) expect(before[id], id).toBeTruthy();
  await page.locator("[data-tour=add-source]").click();
  await node(page, "BB-CABIN-BUS").click();
  await page.getByRole("dialog").getByRole("button", { name: "Add source" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".node-card")).toHaveCount(ids.length + 1);
  await page.waitForTimeout(1200);  // the positions post
  await ready(page);
  await expect(page.locator(".node-card")).toHaveCount(ids.length + 1);
  const after = await flowPos(page);
  for (const id of ids) expect(after[id], id).toEqual(before[id]);  // all of them, so the 5 sample cards too
  const src = Object.keys(after).find((id) => !ids.includes(id))!, bus = after["BB-CABIN-BUS"];
  expect(Math.hypot(after[src][0] - bus[0], after[src][1] - bus[1])).toBeLessThan(300);
});

test("collapsed, the Simulate summary covers no card: every card centre is clickable", async ({ page }) => {
  await ready(page);
  await page.locator("[data-tour=simulate]").click();
  const sum = page.getByRole("region", { name: "Simulation results" });
  await expect(sum.locator(".sim-group").first()).toBeVisible({ timeout: 30_000 });  // open right after Simulate
  await sum.getByRole("button", { expanded: true }).click();
  await expect(sum.locator(".sim-group")).toHaveCount(0);
  await expect(sum.getByRole("button", { name: "Clear" })).toBeVisible();
  await page.mouse.move(150, 600);
  await page.waitForTimeout(600);
  const bad = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>(".node-card")].filter((c) => {
    const r = c.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2;
    return x >= 0 && y >= 0 && x <= innerWidth && y <= innerHeight && !c.contains(document.elementFromPoint(x, y)); }).map((c) => c.dataset.tourNode));
  expect(bad).toEqual([]);
});

test("the summary collapses while a source is being placed and opens again on the next Simulate", async ({ page }) => {
  await ready(page);
  await page.locator("[data-tour=simulate]").click();
  const sum = page.getByRole("region", { name: "Simulation results" });
  await expect(sum.locator(".sim-group").first()).toBeVisible({ timeout: 30_000 });
  await page.locator("[data-tour=add-source]").click();
  await expect(sum.locator(".sim-group")).toHaveCount(0);
  await expect(sum.locator(".sim-chip")).toContainText(/problem/);
  await page.keyboard.press("Escape");
  await page.locator("[data-tour=simulate]").click();
  await expect(sum.locator(".sim-group").first()).toBeVisible({ timeout: 30_000 });
});
