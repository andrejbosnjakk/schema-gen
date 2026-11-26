// Popup cards, simulate overlay and + Source against a real `schemagen app` of its own (the edits and the added source stay in its home folder).
import { expect, test } from "@playwright/test";
import { cardTests } from "./cards.shared";
import { startServer, type Server } from "./server";

let srv: Server;
test.beforeAll(async () => { srv = await startServer(8830); await fetch(srv.url + "api/settings", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ tour_done: true }) }); });
test.afterAll(() => srv?.stop());

cardTests(async (page) => {
  await page.goto(srv.url);
  const ex = page.getByRole("button", { name: "Open the example project" });
  await expect(ex.or(page.locator(".node-card").first())).toBeVisible({ timeout: 20_000 });   // the start screen or the map, once loaded (isVisible does not wait)
  if (await ex.isVisible()) await ex.click();
}, "real");
