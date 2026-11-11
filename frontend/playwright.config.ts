import { defineConfig } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { PYTHON, serverEnv } from "./e2e/server";

// the browser that ships with the environment (CI installs its own with `npx playwright install chromium`)
const exe = process.env.PW_CHROMIUM || undefined;
const smoke = !!process.env.SMOKE_URL;  // run only the smoke test, against a server started elsewhere
const home = fs.mkdtempSync(path.join(os.tmpdir(), "sg-home-"));  // the `real` project's server starts with no project here

// `mock`: the app built with the in-memory server (`--mode mock`, src/mock), served statically, no Python needed.
// `real`: a real `schemagen app` serving the build in schemagen/app/static (run `npm run build` first), starting with no project.
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: { browserName: "chromium", viewport: { width: 1366, height: 768 },
         launchOptions: { ...(exe ? { executablePath: exe } : {}), args: ["--disable-background-networking", "--disable-component-update", "--no-pings"] } },
  projects: smoke ? [{ name: "smoke", testMatch: "smoke.spec.ts" }] : [
    { name: "mock", testMatch: ["app.spec.ts", "cards.spec.ts"], use: { baseURL: "http://127.0.0.1:5199/" } },
    { name: "real", testMatch: ["real.spec.ts", "screens.spec.ts", "cards.real.spec.ts", "tour.spec.ts"], use: { baseURL: "http://127.0.0.1:8799/" } },
  ],
  webServer: smoke ? [] : [
    { command: "npx vite build --mode mock --outDir e2e-dist --emptyOutDir && npx vite preview --outDir e2e-dist --port 5199 --strictPort --host 127.0.0.1",
      url: "http://127.0.0.1:5199/", timeout: 120_000, reuseExistingServer: !process.env.CI },
    { command: `"${PYTHON}" -m schemagen app --port 8799 --no-browser`, url: "http://127.0.0.1:8799/api/health", timeout: 60_000,
      env: serverEnv(home), reuseExistingServer: false },
  ],
});
