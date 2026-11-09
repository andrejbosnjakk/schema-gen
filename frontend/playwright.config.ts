import { defineConfig } from "@playwright/test";

// the browser that ships with the environment (CI installs its own with `npx playwright install chromium`)
const exe = process.env.PW_CHROMIUM || undefined;
const smoke = !!process.env.SMOKE_URL;  // run only the smoke test, against a server started elsewhere

// the app built with the in-memory server (`--mode mock`, src/mock) and served statically: no Python needed
export default defineConfig({
  testDir: "e2e",
  testMatch: smoke ? "smoke.spec.ts" : ["app.spec.ts", "screens.spec.ts"],
  timeout: 60_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: { browserName: "chromium", baseURL: "http://127.0.0.1:5199/", viewport: { width: 1366, height: 768 },
         launchOptions: { ...(exe ? { executablePath: exe } : {}), args: ["--disable-background-networking", "--disable-component-update", "--no-pings"] } },
  webServer: smoke ? [] : [
    { command: "npx vite build --mode mock --outDir e2e-dist --emptyOutDir && npx vite preview --outDir e2e-dist --port 5199 --strictPort --host 127.0.0.1",
      url: "http://127.0.0.1:5199/", timeout: 120_000, reuseExistingServer: !process.env.CI },
  ],
});
