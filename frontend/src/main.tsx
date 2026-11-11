import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./theme";
import "./app.css";

const q = new URLSearchParams(location.search);
// the in-memory server exists only in dev and `--mode mock` builds (the e2e tests); a production build has no mock
const ready = (import.meta.env.DEV || import.meta.env.MODE === "mock") && q.has("mock") ? import("./mock").then((m) => m.install(q)) : Promise.resolve();
ready.then(() => createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>));
