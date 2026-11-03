import { defineConfig } from "@playwright/test";

const py = process.env.PYTHON || "python3";
// the browser that ships with the environment (CI installs its own with `npx playwright install chromium`)
const exe = process.env.PW_CHROMIUM || undefined;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: { browserName: "chromium", launchOptions: exe ? { executablePath: exe } : {}, viewport: { width: 1400, height: 900 } },
  webServer: [
    { command: `${py} e2e/serve.py demo 8801`, url: "http://127.0.0.1:8801/api/index", timeout: 120_000, reuseExistingServer: false },
    { command: `${py} e2e/serve.py synth5k 8802`, url: "http://127.0.0.1:8802/api/index", timeout: 180_000, reuseExistingServer: false },
  ],
});
