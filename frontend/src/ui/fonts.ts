// Self-hosted fonts (Fontsource, SIL Open Font License 1.1), bundled by Vite, no request to a font CDN.
// Every family ships a Vietnamese subset; the browser downloads a subset only when a page uses
// characters in its unicode-range. Families are named in tokens.css (--font-display/-sans/-mono).
import "@fontsource-variable/inter/index.css"; // "Inter Variable", wght 100-900
import "@fontsource-variable/newsreader/opsz.css"; // "Newsreader Variable", wght 200-800 + optical size
import "@fontsource-variable/jetbrains-mono/index.css"; // "JetBrains Mono Variable", wght 100-800

/** The families as they must appear in `document.fonts` once loaded (used by the showcase check). */
export const FONT_FAMILIES = {
  display: "Newsreader Variable",
  sans: "Inter Variable",
  mono: "JetBrains Mono Variable",
} as const;
