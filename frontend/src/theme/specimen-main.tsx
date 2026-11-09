// Throwaway entry for the style sheet page: `npx vite` then open /specimen.html (?theme=dark for dark).
import { createRoot } from "react-dom/client";
import "./index";
import Specimen from "./Specimen";

document.documentElement.dataset.theme = new URLSearchParams(location.search).get("theme") === "dark" ? "dark" : "light";
createRoot(document.getElementById("root")!).render(<Specimen />);
