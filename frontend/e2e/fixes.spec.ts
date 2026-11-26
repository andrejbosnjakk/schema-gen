// The review fixes (tour, selection, wire rows, toasts, cards, + Source and edge paths, export menu, back to the start screen, fit padding)
// against the in-memory mock. SHOTS=<dir> also writes screenshots there.
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const shot = async (p: Page, name: string) => { const d = process.env.SHOTS; if (d) { fs.mkdirSync(d, { recursive: true }); await p.screenshot({ path: path.join(d, `${name}.png`) }); } };
const node = (p: Page, id: string) => p.locator(`.node-card[data-tour-node="${id}"]`);
const open = async (p: Page, q = "") => { await p.goto(`/?mock=1&open=1${q}`); await expect(p.locator(".node-card").first()).toBeVisible(); await p.waitForTimeout(700); };
const theme = (p: Page, t: string) => p.evaluate((x) => { document.documentElement.dataset.theme = x; }, t);
const hit = (a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }) =>
  a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
const noNaN = (p: Page) => p.evaluate(() => [...document.querySelectorAll(".bundle, .bundle-hit")].filter((e) => /NaN/.test(e.getAttribute("d") ?? "")).length);

// ---- A: the tour ----
const pop = (p: Page) => p.locator(".driver-popover.sg-tour");
const title = (p: Page) => pop(p).locator(".driver-popover-title");
const count = (p: Page) => pop(p).locator(".sg-tour-count");

test("A: the tour closes cards between steps, marks W045, and the simulate and source steps have two phases", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Help" }).click();
  await page.getByRole("menuitem", { name: "Replay the tour" }).click();
  await expect(title(page)).toHaveText("Your whole system, one picture");
  await expect(pop(page)).not.toContainText("left to right");
  await expect(pop(page)).toContainText("grouped by subsystem");
  await pop(page).getByRole("button", { name: "Next" }).click();
  await expect(title(page)).toHaveText("Click a component");
  await expect(pop(page)).not.toContainText("current");
  await node(page, "CB-XPDR").click();
  await expect(title(page)).toHaveText("Everything about one part");
  await expect(page.locator(".scrim .dialog")).toBeVisible();
  await pop(page).getByRole("button", { name: "Next" }).click();     // Next with the card still open: the card is closed first
  await expect(title(page)).toHaveText("What is wrong");
  await expect(page.locator(".scrim .dialog")).toHaveCount(0);
  await pop(page).getByRole("button", { name: "Next" }).click();
  await expect(title(page)).toHaveText("The sheet you know");
  await expect(page.locator(".scrim .dialog")).toHaveCount(0);
  await expect(pop(page)).not.toContainText("18 AWG");
  const row = page.locator("[role=row][data-id=W045]");
  await expect(row).toBeVisible();
  await expect(row).toHaveClass(/sel/);
  const drawer = (await page.locator(".tbody").boundingBox())!, r = (await row.boundingBox())!;
  expect(r.y).toBeGreaterThanOrEqual(drawer.y - 1); expect(r.y + r.height).toBeLessThanOrEqual(drawer.y + drawer.height + 1);
  await row.click();                                                  // a row click selects; it opens nothing
  await expect(title(page)).toHaveText("Does it work with power on?");
  await expect(page.locator(".scrim .dialog")).toHaveCount(0);
  await expect(count(page)).toHaveText("6 of 8");
  // simulate: phase 1 waits for the press; phase 2 explains the result and waits for Next
  await expect(pop(page)).toContainText("Press Simulate");
  const sim = page.locator("[data-tour=simulate]"), w0 = (await sim.boundingBox())!.width;
  await sim.click();
  expect((await sim.boundingBox())!.width).toBe(w0);                  // "Simulating…" keeps the button, and so the spotlight, the same size
  await expect(title(page)).toHaveText("What the simulation shows");
  await expect(count(page)).toHaveText("6 of 8");
  await page.waitForTimeout(1500);
  await expect(title(page)).toHaveText("What the simulation shows");   // it does not move on by itself
  const clear = async () => {
    const p = (await pop(page).boundingBox())!, s = (await page.locator("[data-tour=sim-summary]").boundingBox())!;
    expect(hit(p, s), "popover over the summary").toBe(false);
    expect(hit(p, (await node(page, "BB-CABIN-BUS").boundingBox())!), "popover over the cabin bus").toBe(false);
    expect(hit(p, (await page.locator('.zone-node[data-id="zone:Cabin"]').boundingBox())!), "popover over the cabin zone").toBe(false);
    const v = page.viewportSize()!; expect(p.x + p.width).toBeLessThanOrEqual(v.width); expect(p.y + p.height).toBeLessThanOrEqual(v.height);
  };
  await shot(page, "tour-sim-result"); await clear();
  await pop(page).getByRole("button", { name: "Next" }).click();
  await expect(title(page)).toHaveText("Try a fix");
  await expect(count(page)).toHaveText("7 of 8");
  await page.locator("[data-tour=add-source]").click();
  await expect(pop(page)).toBeHidden();                               // steps aside while placing
  await expect(page.getByText("Click a bus or component to attach the source")).toBeVisible();
  await page.keyboard.press("Escape");                                // cancelled: the tour comes back
  await expect(pop(page)).toBeVisible();
  await expect(title(page)).toHaveText("Try a fix");
  await page.locator("[data-tour=add-source]").click();
  await node(page, "BB-CABIN-BUS").click();                           // no stale card in the way
  await page.locator(".scrim .dialog").getByRole("button", { name: "Add source" }).click();
  await expect(title(page)).toHaveText("Press Simulate again");
  await expect(count(page)).toHaveText("7 of 8");
  await shot(page, "tour-source-again");
  await sim.click();
  await expect(title(page)).toHaveText("The cabin bus has power");
  await page.waitForTimeout(1200);
  await expect(title(page)).toHaveText("The cabin bus has power");
  await clear(); await shot(page, "tour-source-result");
  await pop(page).getByRole("button", { name: "Next" }).click();
  await expect(title(page)).toHaveText("Now your own wiring");
});

// ---- B and C: selection ----
test("B: Esc, a click on empty canvas and the same issue again clear the selection; opening a project clears it", async ({ page }) => {
  await open(page);
  const dimmed = () => page.locator(".bundle.dim, .bundle.hl, .node-card.hl").count();
  const issue = page.locator(".issue:not([disabled])").first();
  await issue.click();
  await expect(issue).toHaveClass(/sel/);
  await page.locator("[role=row][data-id]").nth(3).click();
  await expect(page.locator(".node-card.hl")).toHaveCount(2);
  expect(await page.locator(".bundle.dim").count()).toBeGreaterThan(0);
  await page.keyboard.press("Escape");
  await expect.poll(dimmed).toBe(0);
  await page.locator("[role=row][data-id]").nth(3).click();
  await expect(page.locator(".node-card.hl")).toHaveCount(2);
  const blank = await page.evaluate(() => {
    const b = document.querySelector(".react-flow__pane")!.getBoundingClientRect();
    for (let y = b.top + 8; y < b.bottom - 8; y += 6) for (let x = b.left + 8; x < b.right - 8; x += 6)
      if (document.elementFromPoint(x, y)?.classList.contains("react-flow__pane")) return { x, y };
    return null;
  });
  expect(blank).not.toBeNull();
  await page.mouse.click(blank!.x, blank!.y);
  await expect.poll(dimmed).toBe(0);
  await issue.click(); await expect(issue).toHaveClass(/sel/);
  await issue.click(); await expect(issue).not.toHaveClass(/sel/);    // the same issue again
  await page.locator("[role=row][data-id]").nth(3).click();
  await expect(page.locator(".node-card.hl")).toHaveCount(2);
  await page.getByRole("button", { name: "Back to the start screen" }).click();
  await page.getByRole("button", { name: "Open the example project" }).click();
  await expect(page.locator(".node-card").first()).toBeVisible();
  await expect.poll(dimmed).toBe(0);
  await expect(page.locator(".issue.sel")).toHaveCount(0);
});

test("B: Esc with a menu or a dialog open closes that, not the selection", async ({ page }) => {
  await open(page);
  await page.locator("[role=row][data-id]").nth(3).click();
  await page.getByRole("button", { name: "Export" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(page.locator(".node-card.hl")).toHaveCount(2);
});

test("C: a wire row selects and zooms; its label opens the card, nothing else does", async ({ page }) => {
  await open(page);
  const row = page.locator("[role=row][data-id]").nth(4), before = await page.locator(".react-flow__viewport").getAttribute("style");
  await row.click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".node-card.hl")).toHaveCount(2);
  await expect.poll(() => page.locator(".react-flow__viewport").getAttribute("style")).not.toBe(before);
  await row.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const link = row.locator(".link");
  expect(await link.evaluate((e) => getComputedStyle(e).color)).toBe(await page.evaluate(() => { const a = document.createElement("a"); a.style.color = "var(--accent)"; document.body.append(a); const c = getComputedStyle(a).color; a.remove(); return c; }));
  await link.click();
  await expect(page.getByRole("dialog").locator(".kind-chip")).toHaveText("wire");
});

// ---- D: toasts ----
test("D: toasts sit bottom right above the drawer, never over the top bar or menus; they expire; at most 3; a project clears them", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Export" }).click();
  await page.getByRole("menuitem", { name: /Fault sweep/ }).click();
  const t = page.locator(".toast.ok");
  await expect(t).toBeVisible();
  const b = (await t.boundingBox())!, top = (await page.locator(".topbar").boundingBox())!, drawer = (await page.locator(".wires").boundingBox())!, v = page.viewportSize()!;
  expect(b.y).toBeGreaterThan(top.y + top.height); expect(b.y + b.height).toBeLessThanOrEqual(drawer.y); expect(b.x + b.width).toBeLessThanOrEqual(v.width);
  expect(b.x).toBeGreaterThan(v.width / 2);
  await expect(t).toContainText("Fault sweep: 2 files saved.");
  await page.getByRole("button", { name: "Export" }).click();         // the menu is not covered
  await page.getByRole("menuitem", { name: /Wiring checklist/ }).click();
  await expect(page.locator(".toast.ok")).toHaveCount(2);
  for (let i = 0; i < 3; i++) { await page.getByRole("button", { name: "Export" }).click(); await page.getByRole("menuitem", { name: /Wire sheet/ }).click(); }
  expect(await page.locator(".toast").count()).toBeLessThanOrEqual(3);
  await shot(page, "toasts-light");
  await theme(page, "dark"); await page.waitForTimeout(300); await shot(page, "toasts-dark");
  await page.waitForTimeout(6000);
  await expect(page.locator(".toast.ok")).not.toHaveCount(0);        // with an action: still there at 6 s
  await expect(page.locator(".toast.ok")).toHaveCount(0, { timeout: 5000 });   // gone by 8 s
  await page.getByRole("button", { name: "Export" }).click();
  await page.getByRole("menuitem", { name: /Fault sweep/ }).click();
  await expect(page.locator(".toast")).not.toHaveCount(0);
  await page.getByRole("button", { name: "Back to the start screen" }).click();
  await expect(page.locator(".toast")).toHaveCount(0);
});

test("D: an error with Retry stays until closed, and does not survive into the next project", async ({ page }) => {
  await page.goto("/?mock=1&fail=open");
  await page.getByRole("button", { name: "Open the example project" }).click();
  const t = page.locator(".toast.err");
  await expect(t).toContainText("could not be opened");
  await page.waitForTimeout(6000);
  await expect(t).toBeVisible();
  await page.getByRole("button", { name: /Remove .* from the list/ }).count();
  await page.getByRole("button", { name: "Open the example project" }).click();
  await expect(page.locator(".node-card").first()).toBeVisible();
  await expect(page.locator(".toast")).toHaveCount(0);
});

// ---- E: cards ----
for (const [w, h] of [[1366, 768], [1920, 1080]]) for (const t of ["light", "dark"]) {
  test(`E: component cards read first, one scroll area, wrapped drawing (${w}x${h} ${t})`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await open(page);
    await theme(page, t);
    await node(page, "X-FW").click({ force: true });
    const dlg = page.getByRole("dialog");
    await expect(dlg.locator(".pin").first()).toBeVisible();
    const b = (await dlg.boundingBox())!;
    expect(b.width).toBeGreaterThan(700); expect(b.width).toBeLessThanOrEqual(Math.min(920, w - 32) + 1); expect(b.height).toBeLessThanOrEqual(h * 0.85 + 1);
    await expect(dlg.locator(".dw-group")).toHaveText("J1");              // the connector is the heading over its runs
    await expect(dlg.locator(".dw-row .dw-pin strong").first()).toHaveText("1");
    await expect(dlg.locator(".dw-row .dw-wire").first()).toBeVisible(); // the run: pin, wire, where it lands
    await expect(dlg.locator(".dw-row .dw-at").first()).toBeVisible();
    await expect(dlg.locator(".pin-sub").first()).toBeVisible();
    await expect(dlg.getByRole("button", { name: "Edit" })).toBeVisible();
    await expect(dlg.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
    await expect(dlg.getByLabel("Name")).toHaveCount(0);
    // header, then issues (when there are any), then the table
    const order = await dlg.evaluate((d) => ["header", ".card-kind", ".card-issues", ".pin-table"].map((s) => d.querySelector(s)?.getBoundingClientRect().top ?? -1));
    expect(order.filter((y) => y >= 0)).toEqual([...order.filter((y) => y >= 0)].sort((a, c) => a - c));
    // one scroll area: nothing inside the section scrolls by itself, and text is not cut off
    const nested = await dlg.evaluate((d) => [...d.querySelectorAll("section *")].filter((e) => { const o = getComputedStyle(e).overflowY; return (o === "auto" || o === "scroll") && e.scrollHeight > e.clientHeight; }).length);
    expect(nested).toBe(0);
    const cut = await dlg.evaluate((d) => [...d.querySelectorAll(".pin-table .dw-row, .pin-table .dw-row *")].filter((e) => e.scrollWidth > e.clientWidth + 1).length);
    expect(cut).toBe(0);
    expect(await dlg.evaluate((d) => d.scrollWidth <= d.clientWidth && document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await shot(page, `card-xfw-${w}-${t}`);
    await dlg.getByRole("button", { name: "Edit" }).click();            // the fields appear in place; Cancel and Save only now
    await expect(dlg.getByLabel("Name")).toBeVisible();
    await expect(dlg.getByRole("button", { name: "Cancel" })).toBeVisible();
    await expect(dlg.getByRole("button", { name: "Edit" })).toHaveCount(0);
    await shot(page, `card-xfw-edit-${w}-${t}`);
    await dlg.getByRole("button", { name: "Cancel" }).click();
    await expect(dlg.getByLabel("Name")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await node(page, "CB-XPDR").click({ force: true });                 // a breaker (2 pins)
    await expect(page.getByRole("dialog").locator(".pin").first()).toBeVisible();
    await shot(page, `card-breaker-${w}-${t}`);
    await page.keyboard.press("Escape");
    await node(page, "CABIN-FAN").click({ force: true });               // a device
    await expect(page.getByRole("dialog").locator(".pin").first()).toBeVisible();
    await shot(page, `card-device-${w}-${t}`);
    await page.keyboard.press("Escape");
    await page.getByLabel("Filter wires").fill("W045");
    await page.locator("[role=row][data-id=W045]").locator(".link").click();   // a wire: facts first
    const wd = page.getByRole("dialog");
    await expect(wd.locator(".meta")).toContainText("Gauge");
    await expect(wd.getByRole("button", { name: "Edit" })).toBeVisible();
    await shot(page, `card-wire-${w}-${t}`);
  });
}

test("E: a component whose pins are all blank shows no pin numbers", async ({ page }) => {
  await open(page, "&nopins=1");
  await node(page, "CB-XPDR").click({ force: true });
  const dlg = page.getByRole("dialog");
  await expect(dlg.locator(".pin").first()).toBeVisible();
  await expect(dlg.locator(".dw-row .dw-wire").first()).toBeVisible();   // the drawing keeps its rows, with no pin numbers or names
  expect((await dlg.locator(".dw-pin strong, .dw-pin .pin-sub").allTextContents()).join("")).toBe("");
});

// ---- F: edge paths and a new source ----
test("F: no edge path has NaN, in the example, in 8 copies of it, and after adding a source", async ({ page }) => {
  await open(page);
  expect(await noNaN(page)).toBe(0);
  await page.goto("/?mock=1&open=1&wires=1000");
  await expect(page.locator(".node-card").first()).toBeVisible();
  await page.waitForTimeout(800);
  expect(await page.locator(".bundle").count()).toBeGreaterThan(50);
  expect(await noNaN(page)).toBe(0);
});

test("F: + Source lands near its bus, clear of cards and labels, with its edge drawn, and nothing else moves", async ({ page }) => {
  await open(page);
  const pos = () => page.evaluate(() => Object.fromEntries([...document.querySelectorAll(".react-flow__node-card")].map((e) => [e.getAttribute("data-id"), (e as HTMLElement).style.transform])));
  const before = await pos();
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.locator("[data-tour=add-source]").click();
  await node(page, "BB-CABIN-BUS").click();
  await page.getByRole("dialog").getByLabel(/Name/).fill("Cabin battery");
  await page.getByRole("dialog").getByRole("button", { name: "Add source" }).click();
  const src = page.locator(".node-card", { hasText: "Cabin battery" });
  await expect(src).toBeVisible();
  await page.waitForTimeout(900);
  await shot(page, "source-placed");
  const after = await pos();
  for (const [id, t] of Object.entries(before)) expect(after[id], id).toBe(t);   // D95: no other card moved
  const s = (await src.boundingBox())!, bus = (await node(page, "BB-CABIN-BUS").boundingBox())!;
  expect(Math.hypot(s.x - bus.x, s.y - bus.y)).toBeLessThan(330);   // the free spot nearest to the bus (the example is packed tight)
  for (const c of await page.locator(".node-card").all()) { if (await c.isVisible() && (await c.innerText()) !== "Cabin battery") expect(hit(s, (await c.boundingBox())!)).toBe(false); }
  for (const l of await page.locator(".elabel").all()) { const lb = await l.boundingBox(); if (lb) expect(hit(s, lb)).toBe(false); }
  const edge = page.locator('.react-flow__edge[data-id="SRC-1~BB-CABIN-BUS"] .bundle');
  await expect(edge).toHaveCount(1);
  expect(await edge.getAttribute("d")).not.toMatch(/NaN/);
  expect(await noNaN(page)).toBe(0);
  expect(errors.filter((e) => /NaN|attribute d/.test(e))).toEqual([]);
  await shot(page, "source-placed");
});

// ---- G: export menu ----
test("G: the Export menu order and wording; Wiring diagrams is always there and saves the set", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Export" }).click();
  const items = page.getByRole("menuitem");
  expect(await items.allInnerTexts()).toEqual(["Wire sheet\nXLSX, your sheet written back", "Wiring checklist\nprintable, per component", "Fault sweep\nHTML report", "Wiring diagrams\nPDF, every component", "Overview\nPDF, 3 pages"]);
  const diagrams = page.getByRole("menuitem", { name: /Wiring diagrams/ });
  await expect(diagrams).not.toHaveAttribute("aria-disabled", "true");
  await shot(page, "export-menu");
  await diagrams.click();
  await expect(page.locator(".toast.ok")).toContainText("Wiring diagrams: 3 files saved.");
});

// ---- H: back to the start screen ----
test("H: the logo goes back to the start screen; Recent shows name and date; a row can be removed", async ({ page }) => {
  await open(page);
  const logo = page.getByRole("button", { name: "Back to the start screen" });
  await expect(logo).toHaveAttribute("title", "Back to the start screen");
  await logo.click();
  await expect(page.getByRole("button", { name: "Open the example project" })).toBeVisible();
  const rows = page.locator(".recent li");
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText("Kestrel E2");
  await expect(page.locator(".recent")).not.toContainText("examples/aircraft");
  await expect(rows.first().locator(".r-open")).toHaveAttribute("title", "examples/aircraft");
  const x = rows.first().getByRole("button", { name: /Remove/ });
  expect(await x.evaluate((e) => getComputedStyle(e).opacity)).toBe("0");
  await rows.first().hover();
  await expect(x).toBeVisible(); await expect.poll(() => x.evaluate((e) => getComputedStyle(e).opacity)).toBe("1");
  await shot(page, "start-recent-hover");
  await x.click();
  await expect(rows).toHaveCount(1);
  await expect(page.locator(".recent")).not.toContainText("Kestrel E2");
});

test("H: a file with no wires shows the server's message", async ({ page }) => {
  await open(page);
  await page.locator("input[type=file]").setInputFiles({ name: "empty.csv", mimeType: "text/csv", buffer: Buffer.from("label,name,from,to\n") });
  await expect(page.locator(".toast.err")).toContainText("no wires");
});

// ---- I: fit-to-screen leaves room for + Source and the zoom buttons ----
for (const [w, h] of [[1366, 768], [1920, 1080]]) test(`I: after fit to screen no card is under + Source or the zoom buttons (${w}x${h})`, async ({ page }) => {
  await page.setViewportSize({ width: w, height: h });
  await open(page);
  await page.locator("[data-tour=fit]").click();
  await page.waitForTimeout(900);
  const tools = [(await page.locator(".canvas-tools").boundingBox())!, (await page.locator(".zoom-controls").boundingBox())!];
  for (const c of await page.locator(".node-card").all()) { const b = await c.boundingBox(); if (b) for (const t of tools) expect(hit(b, t), await c.innerText()).toBe(false); }
  await shot(page, `fit-${w}`);
});
