import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// built assets ship inside the Python wheel (schemagen/app/static); no CDN at runtime
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "../schemagen/app/static", emptyOutDir: true, chunkSizeWarningLimit: 2000 },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
