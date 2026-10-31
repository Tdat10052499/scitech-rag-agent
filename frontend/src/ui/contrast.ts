// WCAG 2.x contrast ratio, used by the contrast test (static, from tokens.css) and by the showcase
// (live, from computed styles in each theme).

export type Rgb = [number, number, number];

/** Parse "#rgb", "#rrggbb", "rgb(r, g, b)", "rgb(r g b / a)" or "rgba(...)". Alpha is ignored. */
export function parseColor(input: string): Rgb | null {
  const s = input.trim().toLowerCase();
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/.exec(s);
  if (hex) {
    const h = hex[1] ?? "";
    const full = h.length === 3 ? [...h].map((c) => c + c).join("") : h;
    const n = parseInt(full, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const fn = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/.exec(s);
  if (fn) return [Number(fn[1]), Number(fn[2]), Number(fn[3])];
  return null;
}

export function toHex([r, g, b]: Rgb): string {
  return "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
}

function luminance([r, g, b]: Rgb): number {
  const [lr, lg, lb] = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as Rgb;
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

export function contrastRatio(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Foreground/background pairs that the components actually render, with the WCAG AA minimum:
 * 4.5 for text, 3 for icons, control boundaries and the focus ring (WCAG 1.4.11).
 * Disabled controls are exempt and not listed.
 */
export const CONTRAST_PAIRS: ReadonlyArray<{ fg: string; bg: string; min: number; use: string }> = [
  { fg: "--color-text", bg: "--color-bg-canvas", min: 4.5, use: "Answer and body text" },
  { fg: "--color-text", bg: "--color-bg-surface", min: 4.5, use: "User turn, sidebar" },
  { fg: "--color-text", bg: "--color-bg-elevated", min: 4.5, use: "Composer, drawer" },
  { fg: "--color-text", bg: "--color-bg-hover", min: 4.5, use: "Hovered row" },
  { fg: "--color-text", bg: "--color-bg-selected", min: 4.5, use: "Selected source" },
  { fg: "--color-text", bg: "--color-bg-highlight", min: 4.5, use: "Cited source flash" },
  { fg: "--color-text-secondary", bg: "--color-bg-canvas", min: 4.5, use: "Metadata on page" },
  { fg: "--color-text-secondary", bg: "--color-bg-surface", min: 4.5, use: "Metadata in sidebar" },
  { fg: "--color-text-secondary", bg: "--color-bg-elevated", min: 4.5, use: "Composer hint" },
  { fg: "--color-text-secondary", bg: "--color-bg-hover", min: 4.5, use: "Metadata, hovered" },
  { fg: "--color-text-secondary", bg: "--color-bg-selected", min: 4.5, use: "Metadata, selected source" },
  { fg: "--color-text-secondary", bg: "--color-bg-highlight", min: 4.5, use: "Metadata, flash" },
  { fg: "--color-text-link", bg: "--color-bg-canvas", min: 4.5, use: "Source title link" },
  { fg: "--color-text-link", bg: "--color-bg-elevated", min: 4.5, use: "Link in drawer" },
  { fg: "--color-text-link", bg: "--color-bg-selected", min: 4.5, use: "Link, selected source" },
  { fg: "--citation-text", bg: "--citation-bg", min: 4.5, use: "Citation marker" },
  { fg: "--color-text-on-accent", bg: "--color-accent", min: 4.5, use: "Primary button, active citation" },
  { fg: "--color-text-on-accent", bg: "--color-accent-hover", min: 4.5, use: "Primary button, hover" },
  { fg: "--color-warning-text", bg: "--color-warning-bg", min: 4.5, use: "Insufficient evidence" },
  { fg: "--color-text", bg: "--color-warning-bg", min: 4.5, use: "Body in warning callout" },
  { fg: "--color-error-text", bg: "--color-error-bg", min: 4.5, use: "Error title" },
  { fg: "--color-text", bg: "--color-error-bg", min: 4.5, use: "Body in error callout" },
  { fg: "--color-info-text", bg: "--color-info-bg", min: 4.5, use: "Info callout" },
  { fg: "--color-warning-icon", bg: "--color-warning-bg", min: 3, use: "Warning icon" },
  { fg: "--color-error-icon", bg: "--color-error-bg", min: 3, use: "Error icon" },
  { fg: "--color-border-strong", bg: "--color-bg-canvas", min: 3, use: "Control border on page" },
  { fg: "--color-border-strong", bg: "--color-bg-surface", min: 3, use: "Control border in sidebar" },
  { fg: "--color-border-strong", bg: "--color-bg-elevated", min: 3, use: "Composer border" },
  { fg: "--color-focus-ring", bg: "--color-bg-canvas", min: 3, use: "Focus ring on page" },
  { fg: "--color-focus-ring", bg: "--color-bg-surface", min: 3, use: "Focus ring in sidebar" },
  { fg: "--color-focus-ring", bg: "--color-bg-elevated", min: 3, use: "Focus ring in drawer" },
  { fg: "--color-focus-ring", bg: "--color-bg-selected", min: 3, use: "Focus ring, selected source" },
];
