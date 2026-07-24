import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Fuentes RODDOS bundleadas local (regla: sin CDN en runtime).
// Raleway = cuerpo/UI; Montserrat = titulares y cifras.
import "@fontsource/raleway/400.css";
import "@fontsource/raleway/500.css";
import "@fontsource/raleway/600.css";
import "@fontsource/montserrat/600.css";
import "@fontsource/montserrat/700.css";

import App from "@/App";
import "@/index.css";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("No se encontró #root");

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
