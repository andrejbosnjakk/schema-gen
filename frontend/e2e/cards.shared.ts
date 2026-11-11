// Steps 4 to 6 (popup cards, the simulation overlay, + Source) as one set of flows, run against the mock server and the real one.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const serious = (r: { violations: { impact?: string | null }[] }) => r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
const node = (p: Page, id: string) => p.locator(`.node-card[data-tour-node="${id}"]`);
const viewport = (p: Page) => p.locator(".react-flow__viewport").getAttribute("style");
const fits = (p: Page, sel: string) => p.evaluate((s) => { const e = document.querySelector(s)!; return e.scrollWidth <= e.clientWidth; }, sel);

/** `open` shows the main screen with the example project; it is called at the start of every test. */
export function cardTests(open: (p: Page) => Promise<void>, kind: string) {
  test.describe.configure({ mode: "serial" });
  test.beforeEach(async ({ page }) => { await open(page); await expect(node(page, "CB-XPDR")).toBeVisible({ timeout: 20_000 }); await page.waitForTimeout(500); });

  test(`${kind}: a component card opens, edits and saves; the diagram updates in place`, async ({ page }) => {
    const events: string[] = [];
    await page.exposeFunction("seen", (a: string) => events.push(a));
    await page.evaluate(() => window.addEventListener("schemagen:action", (e) => (window as unknown as { seen: (a: string) => void }).seen((e as CustomEvent).detail.action)));
    const view0 = await viewport(page), box0 = await node(page, "CB-XPDR").boundingBox();
    await node(page, "CB-XPDR").click();
    const dlg = page.getByRole("dialog");
    await expect(dlg).toBeVisible();
    await expect(dlg).toHaveAttribute("data-tour", "card");
    await expect(dlg.getByRole("heading", { level: 2 })).toContainText("XPDR");
    await expect(dlg.locator(".kind-chip")).toContainText("breaker");
    await expect(dlg.locator(".pin").first()).toBeVisible();   // pins, with the skeleton gone
    await expect(dlg.locator(".card-issues li").first()).toBeVisible();
    await expect(dlg.getByLabel("Rating (A)")).toHaveValue("15");
    const name = dlg.getByLabel("Name");
    await name.fill("Transponder breaker");
    await dlg.getByRole("button", { name: "Save" }).click();
    await expect(dlg).toHaveCount(0);
    await expect(node(page, "CB-XPDR").locator(".card-name")).toHaveText("Transponder breaker");
    await page.waitForTimeout(400);
    expect(await viewport(page)).toBe(view0);                  // zoom and pan stay
    expect(await node(page, "CB-XPDR").boundingBox()).toEqual(box0);  // and the card does not move
    expect(events).toEqual(expect.arrayContaining(["card-open", "card-close"]));
  });

  test(`${kind}: Esc and the scrim close the card, focus returns, Tab stays inside`, async ({ page }) => {
    await node(page, "CB-XPDR").click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.locator(".pin").first()).toBeVisible();
    for (let i = 0; i < 25; i++) { await page.keyboard.press("Tab"); expect(await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"))).toBe(true); }
    await page.keyboard.press("Escape");
    await expect(dlg).toHaveCount(0);
    await node(page, "CB-XPDR").click();
    await expect(dlg).toBeVisible();
    await page.mouse.click(8, 400);                             // the scrim
    await expect(dlg).toHaveCount(0);
  });

  test(`${kind}: inside a card, a pin's wire and its other end switch the card`, async ({ page }) => {
    await node(page, "CB-XPDR").click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.locator(".pin").first()).toBeVisible();
    await dlg.locator(".pin .link").first().click();
    await expect(dlg.locator(".kind-chip")).toHaveText("wire");
    await dlg.getByRole("button", { name: /Ends/ }).count();
    await dlg.locator(".card-ends .link").first().click();
    await expect(dlg.locator(".kind-chip")).not.toHaveText("wire");
    await expect(dlg).toHaveCount(1);
  });

  test(`${kind}: a wire row opens the wire card; fields save`, async ({ page }) => {
    const row = page.locator("[role=row][data-id]").nth(2);
    const id = await row.getAttribute("data-id");
    await row.click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByLabel("Gauge")).toBeVisible();
    await expect(dlg.locator(".kind-chip")).toHaveText("wire");
    await dlg.getByLabel("Notes").fill("checked on the bench");
    await dlg.getByRole("button", { name: "Save" }).click();
    await expect(dlg).toHaveCount(0);
    await row.click();
    await expect(page.getByRole("dialog").getByLabel("Notes")).toHaveValue("checked on the bench");
    await page.keyboard.press("Escape");
    await expect(page.locator(`[role=row][data-id="${id}"]`)).toBeFocused();   // focus is back where it was
  });

  test(`${kind}: clicking an edge on the diagram opens a wire card`, async ({ page }) => {
    const pt = await page.evaluate(() => {
      for (const el of document.querySelectorAll<SVGPathElement>(".bundle-hit")) {
        const L = el.getTotalLength(), m = el.getScreenCTM()!;
        for (let t = 0.05; t < 1; t += 0.05) {
          const p = el.getPointAtLength(L * t), x = m.a * p.x + m.c * p.y + m.e, y = m.b * p.x + m.d * p.y + m.f;
          if (x > 320 && y > 60 && y < 560 && document.elementFromPoint(x, y) === el) return { x, y };
        }
      }
      return null;
    });
    expect(pt).not.toBeNull();
    await page.mouse.click(pt!.x, pt!.y);
    const menu = page.locator(".edge-menu");
    if (await menu.isVisible().catch(() => false)) await menu.getByRole("menuitem").first().click();
    await expect(page.getByRole("dialog").locator(".kind-chip")).toHaveText("wire");
  });

  test(`${kind}: simulate overlays badges, bars, rings and a summary; a group click zooms; Clear removes it`, async ({ page }) => {
    const events: string[] = [];
    await page.exposeFunction("seen", (a: string) => events.push(a));
    await page.evaluate(() => window.addEventListener("schemagen:action", (e) => (window as unknown as { seen: (a: string) => void }).seen((e as CustomEvent).detail.action)));
    const btn = page.locator("[data-tour=simulate]");
    await btn.click();
    await expect(btn).toHaveAttribute("aria-busy", "true");
    const sum = page.getByRole("region", { name: "Simulation results" });
    await expect(sum).toBeVisible({ timeout: 30_000 });
    await expect(sum.locator(".sim-text")).toContainText(/problem/);
    expect(await page.locator(".v-badge").count()).toBeGreaterThanOrEqual(3);
    await expect(node(page, "BB-CABIN-BUS").locator(".v-badge.low")).toContainText("0.0 V");
    expect(await page.locator(".load-bar").count()).toBeGreaterThanOrEqual(3);
    expect(await page.locator(".node-card.ring-error").count()).toBeGreaterThanOrEqual(1);
    expect(await sum.locator(".sim-group").count()).toBeGreaterThanOrEqual(2);
    // the card shows that object's reason as a status line
    await node(page, "BB-CABIN-BUS").click({ force: true });
    await expect(page.getByRole("dialog").locator(".card-status")).toContainText(/no source/i);
    await page.keyboard.press("Escape");
    const before = await viewport(page);
    await sum.locator(".sim-group", { hasText: /cabin/i }).first().click();
    await expect(page.locator(".node-card.anim-pulse").first()).toBeVisible();
    await expect.poll(() => viewport(page)).not.toBe(before);
    await sum.getByRole("button", { name: "Clear" }).click();
    await expect(sum).toHaveCount(0);
    await expect(page.locator(".v-badge")).toHaveCount(0);
    expect(events).toEqual(expect.arrayContaining(["simulate-done", "simulate-clear"]));
  });

  test(`${kind}: after an edit the overlay is marked out of date until simulating again`, async ({ page }) => {
    await page.locator("[data-tour=simulate]").click();
    const sum = page.getByRole("region", { name: "Simulation results" });
    await expect(sum).toBeVisible({ timeout: 30_000 });
    await expect(sum).not.toContainText("out of date");
    await page.locator("[role=row][data-id]").nth(1).click();
    await page.getByRole("dialog").getByLabel("Notes").fill("edited after simulating");
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await expect(sum).toContainText("Results are out of date, simulate again");
    await expect(page.locator(".flow.stale")).toHaveCount(1);
    await page.locator("[data-tour=simulate]").click();
    await expect(sum).not.toContainText("out of date", { timeout: 30_000 });
    await expect(page.locator(".flow.stale")).toHaveCount(0);
  });

  test(`${kind}: + Source on the cabin bus makes its problem disappear`, async ({ page }) => {
    const events: string[] = [];
    await page.exposeFunction("seen", (a: string) => events.push(a));
    await page.evaluate(() => window.addEventListener("schemagen:action", (e) => (window as unknown as { seen: (a: string) => void }).seen((e as CustomEvent).detail.action)));
    await page.locator("[data-tour=simulate]").click();
    const sum = page.getByRole("region", { name: "Simulation results" });
    await expect(sum.locator(".sim-group", { hasText: /cabin/i }).first()).toBeVisible({ timeout: 30_000 });
    const add = page.locator("[data-tour=add-source]");
    await add.click();
    await expect(page.getByText("Click a bus or component to attach the source")).toBeVisible();
    await page.keyboard.press("Escape");                        // Esc cancels
    await expect(page.getByText("Click a bus or component to attach the source")).toHaveCount(0);
    await add.click();
    await node(page, "BB-CABIN-BUS").click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByRole("heading", { level: 2 })).toHaveText("Add a source");
    await expect(dlg.getByLabel("Type")).toHaveValue("battery");
    await expect(dlg.getByLabel(/Nominal voltage/)).toHaveValue("14");   // the bus's class voltage
    await expect(dlg.getByLabel(/Internal resistance/)).toBeVisible();
    await dlg.getByLabel("Type").selectOption("dcdc");
    await expect(dlg.getByLabel(/Current limit/)).toBeVisible();
    await dlg.getByLabel("Type").selectOption("battery");
    await dlg.getByLabel(/Name/).fill("Cabin battery");
    await dlg.getByRole("button", { name: "Add source" }).click();
    await expect(dlg).toHaveCount(0);
    await expect(page.locator(".node-card", { hasText: "Cabin battery" })).toBeVisible();
    await expect(page.locator(".bundle-g")).not.toHaveCount(0);
    await expect(sum).toContainText("out of date");
    await page.locator("[data-tour=simulate]").click();
    await expect(sum).not.toContainText("out of date", { timeout: 30_000 });
    await expect(sum.locator(".sim-group", { hasText: /cabin/i })).toHaveCount(0);
    await expect(node(page, "BB-CABIN-BUS").locator(".v-badge")).not.toHaveClass(/low/);
    expect(events).toContain("source-added");
    // and the source can be removed from its card
    await page.locator(".node-card", { hasText: "Cabin battery" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Remove source" }).click();
    await expect(page.locator(".node-card", { hasText: "Cabin battery" })).toHaveCount(0);
  });

  test(`${kind}: a card fits 1366x768 with no sideways scroll; axe is clean with the dialog open`, async ({ page }) => {
    await node(page, "CB-XPDR").click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.locator(".pin").first()).toBeVisible();
    const b = (await dlg.boundingBox())!;
    expect(b.y).toBeGreaterThanOrEqual(0); expect(b.y + b.height).toBeLessThanOrEqual(768); expect(b.x + b.width).toBeLessThanOrEqual(1366);
    for (const sel of ["html", ".dialog", ".dialog > section", ".pins", ".wires"]) expect(await fits(page, sel), sel).toBe(true);
    for (const t of ["light", "dark"]) {
      await page.evaluate((x) => { document.documentElement.dataset.theme = x; }, t);
      await page.waitForTimeout(500);
      expect(serious(await new AxeBuilder({ page }).analyze()), `card ${t}`).toEqual([]);
    }
    await page.keyboard.press("Escape");
    await page.locator("[role=row][data-id]").first().click();
    await expect(page.getByRole("dialog").getByLabel("Gauge")).toBeVisible();
    await page.waitForTimeout(400);
    expect(serious(await new AxeBuilder({ page }).analyze()), "wire card dark").toEqual([]);
    expect(await fits(page, ".dialog"), "wire card").toBe(true);
    await page.keyboard.press("Escape");
    await page.locator("[data-tour=add-source]").click();
    await node(page, "BB-CABIN-BUS").click();
    await expect(page.getByRole("dialog").getByLabel("Type")).toBeVisible();
    await page.waitForTimeout(400);
    expect(serious(await new AxeBuilder({ page }).analyze()), "source dialog dark").toEqual([]);
  });
}
