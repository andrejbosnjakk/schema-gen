// Popup cards, simulate overlay and + Source against the in-memory mock server.
import { cardTests } from "./cards.shared";

cardTests(async (page) => { await page.goto("/?mock=1&open=1"); }, "mock");
