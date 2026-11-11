// Starts a real `schemagen app` (fresh SCHEMAGEN_HOME, no project) for the specs that need their own server.
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const VENV = path.resolve(ROOT, "../../../.venv/Scripts/python.exe");  // the main checkout's, when this is a worktree
export const PYTHON = process.env.SG_PYTHON || (fs.existsSync(VENV) ? VENV : "python");
export const serverEnv = (home: string) => ({ ...process.env, PYTHONPATH: ROOT, SCHEMAGEN_HOME: home }) as Record<string, string>;

export interface Server { url: string; home: string; stop: () => void }

/** Spawns the app on `port` and waits until /api/health answers. `recent` seeds the start screen's Recent list with empty projects under `base`. */
export async function startServer(port: number, recent: { name: string; opened: string }[] = [], base = os.tmpdir()): Promise<Server> {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "sg-home-"));
  if (recent.length) {
    const list = recent.map((r) => { const p = path.join(base, r.name); fs.mkdirSync(p, { recursive: true }); fs.writeFileSync(path.join(p, "schemagen.yml"), ""); return { ...r, path: p }; });
    fs.writeFileSync(path.join(home, "settings.json"), JSON.stringify({ recent: list, tour_done: true }));
  }
  const p: ChildProcess = spawn(PYTHON, ["-m", "schemagen", "app", "--port", String(port), "--no-browser"], { env: serverEnv(home), stdio: "ignore" });
  const url = `http://127.0.0.1:${port}/`;
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(url + "api/health")).ok) break; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  return { url, home, stop: () => { p.kill(); try { fs.rmSync(home, { recursive: true, force: true }); } catch { /* log still open */ } } };
}
