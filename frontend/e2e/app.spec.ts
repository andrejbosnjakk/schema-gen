import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";

const DEMO = "http://127.0.0.1:8801/";
const BIG = "http://127.0.0.1:8802/";
const metrics: Record<string, unknown> = existsSync("e2e-results/metrics.json") ? JSON.parse(readFileSync("e2e-results/metrics.json", "utf8")) : {};
const record = (k: string, v: unknown) => { metrics[k] = v; mkdirSync("e2e-results", { recursive: true }); writeFileSync("e2e-results/metrics.json", JSON.stringify(metrics, null, 1)); };

async function search(page: Page, q: string) {
  await page.getByRole("navigation", { name: "Views" }).waitFor();  // the project is loaded
  await page.keyboard.press("Control+k");
  const box = page.getByRole("dialog", { name: "Search every object" }).getByRole("searchbox");
  await box.fill(q);
  return page.getByRole("listbox", { name: "Results" });
}

async function row(page: Page, label: string) { return page.locator(`tr:has(th a:text-is("${label}"))`); }
/** The row with its editors: only the selected row has them. */
async function editRow(page: Page, label: string) { const r = await row(page, label); await r.getByRole("button", { name: `edit ${label}` }).click(); return r; }

// ---------------------------------------------------------------- cold start first, while the machine is idle
test("cold start to interactive on synthetic 5k", async ({ page }) => {
  const ix = await (await page.request.get(BIG + "api/index")).json();
  const t0 = Date.now();
  const p = spawn(process.env.PYTHON || "python3", ["-m", "schemagen", "app", ix.project.root, "--no-browser", "--port", "8803"], { stdio: "ignore", cwd: ".." });
  try {
    for (;;) {
      try { if ((await page.request.get("http://127.0.0.1:8803/api/health", { timeout: 1000 })).ok()) break; } catch { /* starting */ }
      await new Promise((r) => setTimeout(r, 50));
    }
    await page.goto("http://127.0.0.1:8803/");
    await expect(page.locator('tr[data-id] th a').first()).toBeVisible();
    await page.getByLabel("Filter wires").fill("P0001");
    await expect(page.locator("tr[data-id]").first()).toBeVisible();
    const ms = Date.now() - t0;
    record("cold_start_ms_5k", ms);
    expect(ms).toBeLessThanOrEqual(3000);
  } finally { p.kill(); }
});

// ---------------------------------------------------------------- the ten flows
test("search finds a component and opens it", async ({ page }) => {
  await page.goto(DEMO);
  const res = await search(page, "ECU engine");
  await expect(res.getByRole("option").first()).toContainText("ECU");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("ECU engine control unit");
});

test("display names from display.py show in the wire table and on object pages", async ({ page }) => {
  await page.goto(DEMO + "#/table");
  await page.getByLabel("Filter wires").fill("Cockpit display");
  const pin = page.locator('[data-pin="DSP/CAN/H"]').first();
  await expect(pin).toHaveText("Cockpit display (DSP) CAN H");
  await expect(pin).toHaveAttribute("title", /DSP\/CAN\/H/);  // the code stays one hover away
  await page.goto(DEMO + "#/object/component/DSP");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Cockpit display (DSP)");
  await page.goto(DEMO + "#/table");
  await page.getByText("Columns", { exact: true }).click();
  await page.getByRole("checkbox", { name: "colour" }).uncheck();
  await expect(page.getByRole("columnheader", { name: "colour" })).toHaveCount(0);
  await page.getByRole("checkbox", { name: "colour" }).check();
});

test("open object: a pin page shows links, issues and history", async ({ page }) => {
  await page.goto(DEMO + "#/object/conductor/PWR-ECU-B");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("L09");
  await page.getByRole("link", { name: "to ECU engine control unit J1 1" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("ECU engine control unit J1 1");
  await expect(page.getByRole("heading", { name: "Links" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Issues" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  await expect(page.getByText("VBAT")).toBeVisible();  // pin name from the ECU card
});

test("edit and save writes a change set; undo removes it", async ({ page, request }) => {
  await page.goto(DEMO);
  const r = await editRow(page, "L04");
  await r.getByLabel("gauge of L04").selectOption("18");
  await expect(page.getByRole("button", { name: "Save (1)" })).toBeEnabled();
  await page.getByRole("button", { name: /^Save/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "saved 1 change" })).toBeVisible();
  let ix = await (await request.get(DEMO + "api/index")).json();
  expect(ix.project.changes.length).toBe(1);
  expect(ix.conductors.find((c: { id: string }) => c.id === "PWR-ECU-A").gauge).toBe("18");
  await page.reload();
  await expect((await editRow(page, "L04")).getByLabel("gauge of L04")).toHaveValue("18");
  // undo
  await page.getByRole("button", { name: "Undo last change set" }).click();
  await expect(page.getByRole("status").filter({ hasText: "undone" })).toBeVisible();
  await expect((await row(page, "L04")).getByLabel("gauge of L04")).toHaveValue("20");
  ix = await (await request.get(DEMO + "api/index")).json();
  expect(ix.project.changes.length).toBe(0);
});

test("workspace shell: rail, navigator, inspector, problems, Omnibar commands, hotkeys", async ({ page }) => {
  await page.goto(DEMO);
  await expect(page.getByRole("navigation", { name: "Views" }).getByRole("link")).toHaveCount(6);
  await expect(page.getByRole("region", { name: "Problems" })).toBeVisible();
  // plain text table: editors only on the selected row
  await expect(page.locator("tr[data-id] select")).toHaveCount(0);
  await (await row(page, "L09")).locator("td").nth(3).click();
  await expect(page.locator("tr[data-id] select")).toHaveCount(3);
  await expect(page.getByRole("complementary", { name: "Inspector" })).toContainText("L09");
  // navigator: a component selects into the inspector
  const nav = page.getByRole("complementary", { name: "Navigator" });
  await nav.getByRole("button", { name: /^Devices/ }).click();
  await nav.getByRole("button", { name: /ECU engine control unit/ }).click();
  await expect(page.getByRole("complementary", { name: "Inspector" }).getByRole("heading", { level: 3 })).toContainText("ECU");
  for (const theme of ["light", "dark"]) {  // the open navigator, the inspector and a row with its editors
    await page.getByLabel("Theme").selectOption(theme);
    const bad = (await new AxeBuilder({ page }).analyze()).violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(bad.map((v) => `${v.id}: ${v.nodes.slice(0, 2).map((n) => n.target).join(" ")}`), `shell ${theme}`).toEqual([]);
  }
  await page.getByLabel("Theme").selectOption("light");
  await page.setViewportSize({ width: 1440, height: 860 });
  await page.getByTestId("wire-scroll").evaluate((e) => { e.scrollLeft = 0; });
  await page.screenshot({ path: "e2e-results/shell.png" });
  // Omnibar commands and hotkeys
  const res = await search(page, "> issues");
  await res.getByRole("option").first().click();
  await expect(page).toHaveURL(/#\/issues$/);
  await page.keyboard.press("Alt+1");
  await expect(page).toHaveURL(/#\/table$/);
  await page.keyboard.press("BracketRight");
  await expect(page.getByRole("complementary", { name: "Inspector" })).toHaveCount(0);
  await page.keyboard.press("BracketRight");
  await expect(page.getByRole("complementary", { name: "Inspector" })).toBeVisible();
});

test("system canvas: dagre cards, click to inspect, layout metrics", async ({ page }) => {
  const out: Record<string, unknown> = {};
  for (const [url, name] of [[DEMO, "demo"], [BIG, "synth5k"]]) {
    await page.goto(url + "#/graph");
    const sec = page.locator("section.graph[data-crossings]");
    await expect(sec).toBeVisible({ timeout: 30_000 });
    out[name] = { nodes: Number(await sec.getAttribute("data-nodes")), layout_ms: Number(await sec.getAttribute("data-layout-ms")),
                  crossings: Number(await sec.getAttribute("data-crossings")) };
  }
  record("system_canvas", out);
  await page.goto(DEMO + "#/graph");
  await page.locator(".react-flow__node", { hasText: "ECU engine control unit" }).click();
  await expect(page.getByRole("complementary", { name: "Inspector" }).getByRole("heading", { level: 3 })).toContainText("ECU");
  await page.setViewportSize({ width: 1440, height: 860 });
  await page.getByLabel("Which components").selectOption("all");
  await page.waitForTimeout(500);
  await page.screenshot({ path: "e2e-results/system-canvas.png" });
});

test("undo via the changes view", async ({ page, request }) => {
  await request.post(DEMO + "api/edit", { data: { edits: [{ id: "PWR-OTS-C", field: "st", value: "Released" }] } });
  await page.goto(DEMO + "#/diff");
  await expect(page.getByText("edit 1 field(s) in the app")).toBeVisible();
  await page.getByRole("button", { name: "Undo last change set" }).click();
  await expect(page.getByText("Stored change sets 0")).toBeVisible();
});

test("net highlight: a pin lights up its whole net in the table", async ({ page }) => {
  await page.goto(DEMO);
  await page.locator('[data-pin="ECU/J1/2"]').first().click();
  await expect(page.getByRole("status").filter({ hasText: "highlighted" })).toBeVisible();
  for (const l of ["L03", "L11", "L12"]) await expect(await row(page, l)).toHaveClass(/hl/);
  await expect(await row(page, "L05")).not.toHaveClass(/hl/);
});

test("run a scenario", async ({ page }) => {
  await page.goto(DEMO + "#/sim");
  await page.getByLabel("Scenario").selectOption("normal.yml");
  await page.getByRole("button", { name: "Run scenario" }).click();
  await expect(page.getByTestId("sim-status")).toContainText("PASS");
  await expect(page.getByText("ECU: ").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Assumptions" })).toBeVisible();
  await page.getByRole("button", { name: "Fault sweep" }).click();
  await expect(page.getByTestId("sweep")).toBeVisible();
});

test("open a drawing and click a wire label", async ({ page }) => {
  await page.goto(DEMO + "#/drawings");
  if (await page.getByText("No drawings yet").isVisible().catch(() => false)) await page.getByRole("button", { name: "Render drawings" }).click();
  await page.getByLabel("Drawing", { exact: true }).selectOption("X-BH");
  const wire = page.locator('[data-testid="drawing"] text.wire[data-id="PWR-ECU-C1"]').first();
  await expect(wire).toBeVisible({ timeout: 30_000 });
  await wire.click();
  await expect(page.locator('[data-testid="drawing"] text.wire.hl').first()).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "highlighted" })).toBeVisible();
});

test("fix direction: preview, then apply as a change set", async ({ page, request }) => {
  await page.goto(DEMO + "#/diff");
  await page.getByRole("button", { name: "Preview fix" }).click();
  const pv = page.getByTestId("fix-preview");
  await expect(pv).toContainText("L03");
  await expect(pv).toContainText("returns go device");
  await pv.getByRole("button", { name: "Apply as a change set" }).click();
  await expect(page.getByRole("status").filter({ hasText: "direction fixed on 1" })).toBeVisible();
  const ix = await (await request.get(DEMO + "api/index")).json();
  expect(ix.issues.filter((i: { rule: string }) => i.rule === "direction").length).toBe(0);
  await request.post(DEMO + "api/undo");
});

test("diff view against the git revision", async ({ page, request }) => {
  await request.post(DEMO + "api/edit", { data: { edits: [{ id: "PWR-ECU-A", field: "awg", value: "18" }] } });
  await page.goto(DEMO + "#/diff");
  await page.getByRole("button", { name: "Show diff" }).click();
  await expect(page.getByTestId("diff-text")).toContainText("~ conductor PWR-ECU-A gauge: '20' -> '18'");
  await request.post(DEMO + "api/undo");
});

test("issues board filters by severity and rule", async ({ page }) => {
  await page.goto(DEMO + "#/issues");
  const t = page.getByTestId("issues-table");
  await page.getByRole("button", { name: /^warning/ }).click();
  await expect(t.locator("tbody tr").first()).toContainText("warning");
  for (const r of await t.locator("tbody tr").all()) await expect(r).not.toContainText("info");
  await page.getByRole("button", { name: /^all/ }).click();
  await page.getByLabel("Rule").selectOption("open-item");
  await expect(t.locator("tbody tr")).toHaveCount(1);
  await expect(t).toContainText("O-01");
});

// ---------------------------------------------------------------- metrics
test("every object type is reachable in two clicks from search", async ({ page }) => {
  const ix = await (await page.request.get(BIG + "api/index")).json();
  const c = ix.conductors[100];
  const cases: [string, string, RegExp][] = [
    [c.label, "conductor", new RegExp(c.label)],
    [`pin ${c.t[0]} ${c.t[1]} ${c.t[2]}`, "pin", new RegExp(c.t[0])],
    ["BB1 14 V", "component", /BB1/],
    [ix.connectors[0].id, "connector", new RegExp(ix.connectors[0].id)],
    [`harness ${ix.harnesses[0].id}`, "harness", /harness/],
    [`net ${ix.nets[0].name}`, "net", /net/],
    ["part SV-ECU-8", "part", /SV-ECU-8/],
  ];
  await page.goto(BIG);
  const clicks: Record<string, number> = {};
  for (const [q, type, title] of cases) {
    const res = await search(page, q);                                       // click 1: open search (Ctrl K)
    await res.getByRole("option").filter({ has: page.locator(`.tag.${type}`) }).first().click();  // click 2: the result
    await expect(page.getByRole("heading", { level: 1 })).toContainText(title);
    clicks[type] = 2;
  }
  record("clicks_from_search", clicks);
});

test("net highlight within 100 ms on synthetic 5k", async ({ page }) => {
  await page.goto(BIG);
  await expect(page.locator('tr[data-id]').first()).toBeVisible();
  const times: number[] = [];
  for (const k of [0, 1, 2, 3, 4]) {
    await page.locator("[data-pin]").nth(k * 2).click();
    await page.waitForFunction(() => document.body.dataset.highlightMs !== undefined);
    times.push(Number(await page.evaluate(() => document.body.dataset.highlightMs)));
    await page.evaluate(() => { delete document.body.dataset.highlightMs; });
  }
  record("net_highlight_ms_5k", times);
  expect(Math.max(...times)).toBeLessThanOrEqual(100);
});

test("accessibility: no serious or critical axe violations on the main pages", async ({ page }) => {
  const out: Record<string, number> = {};
  for (const h of ["#/table", "#/object/conductor/PWR-ECU-A", "#/object/pin/ECU%2FJ1%2F1", "#/issues", "#/graph", "#/sim", "#/diff", "#/drawings"]) {
    await page.goto(DEMO + h);
    await page.waitForTimeout(500);
    for (const theme of ["light", "dark"]) {
      await page.getByLabel("Theme").selectOption(theme);
      const r = await new AxeBuilder({ page }).exclude(".svgbox").exclude(".cy").analyze();
      const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      out[`${h} ${theme}`] = bad.length;
      expect(bad.map((v) => `${v.id}: ${v.nodes.slice(0, 2).map((n) => n.target).join(" ")}`), `${h} ${theme}`).toEqual([]);
    }
  }
  record("axe_serious_critical", out);
});
