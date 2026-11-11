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

// ---- the polish pass: readable diagram, calmer edges, compact drawer ----
const zoomOf = (p: Page) => p.evaluate(() => new DOMMatrix(getComputedStyle(document.querySelector(".react-flow__viewport")!).transform).a);

test("fit-to-screen at 1366x768 is readable: zoom at least 0.8, card names at least 11 px", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await expect(page.locator(".node-card").first()).toBeVisible();
  await page.waitForTimeout(600);
  const z = await zoomOf(page);
  const px = await page.evaluate((z) => parseFloat(getComputedStyle(document.querySelector(".card-name")!).fontSize) * z, z);
  console.log(`mock fit zoom ${z.toFixed(2)}, card name ${px.toFixed(1)} px`);
  expect(z).toBeGreaterThanOrEqual(0.8);
  expect(px).toBeGreaterThanOrEqual(11);
});

test("edges rest at about 55 % opacity; hovering one emphasises it and dims the rest", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await expect(page.locator(".bundle:not(.ground)").first()).toBeVisible();
  expect(await page.locator(".bundle:not(.ground)").first().evaluate((e) => parseFloat(getComputedStyle(e).opacity))).toBeCloseTo(0.55, 1);
  // a point on some edge that nothing else covers (cards sit above edges)
  const pt = await page.evaluate(() => {
    for (const el of document.querySelectorAll<SVGPathElement>(".bundle-hit")) {
      const L = el.getTotalLength(), m = el.getScreenCTM()!;
      for (let t = 0.05; t < 1; t += 0.05) {
        const p = el.getPointAtLength(L * t), x = m.a * p.x + m.c * p.y + m.e, y = m.b * p.x + m.d * p.y + m.f;
        if (document.elementFromPoint(x, y) === el) return { x, y, id: el.parentElement!.querySelector(".bundle")!.closest("[data-testid]")?.getAttribute("data-testid") ?? "", i: [...document.querySelectorAll(".bundle-hit")].indexOf(el) };
      }
    }
    return null;
  });
  expect(pt).not.toBeNull();
  await page.mouse.move(pt!.x, pt!.y);
  await page.waitForTimeout(300);
  const ops = await page.locator(".bundle-g").evaluateAll((gs) => gs.map((g) => parseFloat(getComputedStyle(g.querySelector(".bundle")!).opacity)));
  expect(ops[pt!.i]).toBeGreaterThan(0.9);
  expect(ops.filter((o, i) => i !== pt!.i && o < 0.3).length).toBeGreaterThan(0);
});

test("dark theme: every edge and table dot has contrast of at least 3:1 with its surface", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  await expect(page.locator(".bundle").first()).toBeVisible();
  await page.evaluate(() => { document.documentElement.dataset.theme = "dark"; });
  await page.waitForTimeout(500);
  const low = await page.evaluate(() => {
    const rgb = (s: string) => (/(\d+)[ ,]+(\d+)[ ,]+(\d+)/.exec(s) ?? []).slice(1, 4).map(Number);
    const lum = (c: number[]) => { const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
    const cr = (a: number[], b: number[]) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
    const canvas = rgb(getComputedStyle(document.querySelector(".canvas")!).backgroundColor), bg = rgb(getComputedStyle(document.body).backgroundColor);
    const out: string[] = [];
    document.querySelectorAll(".bundle").forEach((e) => { const c = rgb(getComputedStyle(e).stroke); if (cr(c, canvas) < 3) out.push(`edge ${c}`); });
    document.querySelectorAll(".tbody .swatch").forEach((e) => { const c = rgb(getComputedStyle(e).backgroundColor); if (cr(c, bg) < 3) out.push(`dot ${c}`); });
    return out;
  });
  expect(low).toEqual([]);
});

test("the Wires drawer starts compact, resizes by its handle, and remembers the height", async ({ page }) => {
  await page.goto("/?mock=1&open=1");
  const wires = page.locator(".wires");
  await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
  const h0 = (await wires.boundingBox())!.height;
  expect(h0).toBeLessThanOrEqual(768 * 0.28);
  const grip = page.getByRole("separator", { name: "Resize the wire list" });
  const g = (await grip.boundingBox())!;
  await page.mouse.move(g.x + g.width / 2, g.y + 4); await page.mouse.down(); await page.mouse.move(g.x + g.width / 2, g.y - 100, { steps: 5 }); await page.mouse.up();
  const h1 = (await wires.boundingBox())!.height;
  expect(h1).toBeGreaterThan(h0 + 80);
  await page.reload();
  await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
  expect(Math.abs((await wires.boundingBox())!.height - h1)).toBeLessThan(2);
  await grip.focus(); await page.keyboard.press("ArrowDown");
  expect((await wires.boundingBox())!.height).toBeLessThan(h1);
  for (const sel of ["html", ".tbody"]) expect(await noSideScroll(page, sel), sel).toBe(true);
});

test("a drawer height that cannot be stored still works (no localStorage)", async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(window, "localStorage", { get() { throw new Error("blocked"); } }); });
  await page.goto("/?mock=1&open=1");
  await expect(page.locator("[role=row][data-id]").first()).toBeVisible();
  expect((await page.locator(".wires").boundingBox())!.height).toBeLessThanOrEqual(768 * 0.28);
});
