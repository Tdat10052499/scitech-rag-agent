import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../ui/fonts";
import "../ui/styles.css";
import "./showcase.css";
import Showcase from "./Showcase";
import Specimen from "./Specimen";

// Entry of showcase.html (dev server only; `npm run build` builds index.html, so none of this ships).
const view = new URLSearchParams(location.search).get("view");

createRoot(document.getElementById("root")!).render(<StrictMode>{view === "specimen" ? <Specimen /> : <Showcase />}</StrictMode>);
