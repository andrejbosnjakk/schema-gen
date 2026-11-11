// Popup cards, simulate overlay and + Source against a real `schemagen app` of its own (the edits and the added source stay in its home folder).
import { test } from "@playwright/test";
import { cardTests } from "./cards.shared";
import { startServer, type Server } from "./server";

let srv: Server;
test.beforeAll(async () => { srv = await startServer(8830); await fetch(srv.url + "api/settings", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ tour_done: true }) }); });
test.afterAll(() => srv?.stop());

cardTests(async (page) => {
  await page.goto(srv.url);
  const ex = page.getByRole("button", { name: "Open the example project" });
  if (await ex.isVisible({ timeout: 3000 }).catch(() => false)) await ex.click();
}, "real");
