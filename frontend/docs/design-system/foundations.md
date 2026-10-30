# Foundations: principles, tokens, theme, typography

Status: **APPROVED BASELINE (2026-10-21)**. Source of truth: `src/ui/tokens.css`.

## Principles

1. **Evidence first.** The answer and its sources are the product. Everything else is quiet.
2. **Reading, not chatting.** Answers sit on the page in a column of at most 760px, not in bubbles.
   Only the user's question gets a light block, so turns stay easy to tell apart.
3. **Say it in words.** Every state (insufficient evidence, error, selected source, missing
   citation) has text or a shape change, never color alone.
4. **Show only what the data says.** No confidence %, no "verified" badge, no retrieval score (no
   common scale across retrievers, not calibrated). Missing metadata is left out, not invented.
5. **Restraint.** Warm neutrals, one sage accent, thin borders, shadows only on floating layers,
   motion only where it explains a change (drawer slide, cited-source flash).

References used and how: Elicit (reading column, typographic hierarchy, follow-up list),
Paperguide (sidebar | conversation | sources workspace, paper metadata hierarchy), DESIGN-claude.md
(warm canvas, serif display, radius scale, restraint; its marketing parts — hero, pricing, footer,
logo, 96px section spacing, coral — are not used). Behaviour not visible in static screenshots
(animations, focus handling) is our own proposal.

## Token layers

| Layer | Prefix | Rule |
|---|---|---|
| Primitive | `--paper-*`, `--ink-*`, `--sage-*`, `--amber-*`, `--red-*`, `--blue-*` | Raw values. Never used in components. |
| Semantic | `--color-*`, `--font-*`, `--text-*`, `--weight-*`, `--space-*`, `--radius-*`, `--shadow-*`, `--duration-*`, `--ease-*`, `--layout-*`, `--z-*` | The only values components and layouts use. |
| Component | `--citation-bg`, `--citation-text` | Only when a component needs a value that is not a general role. |

Theme: each semantic color is `light-dark(<light>, <dark>)`. `color-scheme` decides which side
applies: the OS preference by default, or `data-theme="light" | "dark"` on `<html>` (or on any
subtree). Requires Chrome/Edge 123+, Firefox 120+, Safari 17.5+. The choice is stored in
`localStorage["scitech-theme"]`; storage failures fall back to "system".

## Color

Starting palette from the brief, kept as given except where noted. All text pairs that components
render meet WCAG AA in both themes; the list and the check live in `src/ui/contrast.ts` and
`src/ui/contrast.test.ts` (run by `npm test`) and are shown live in the showcase.

| Role | Light | Dark |
|---|---|---|
| `--color-bg-canvas` | `#FAF9F5` | `#191C19` |
| `--color-bg-surface` | `#F2F1EB` | `#222722` |
| `--color-bg-elevated` | `#FFFFFF` | `#2A302A` |
| `--color-text` | `#242824` (14.2:1 on canvas) | `#F0F1EA` (15.1:1) |
| `--color-text-secondary` | `#626A63` (5.3:1 canvas, 4.9:1 surface) | `#ADB5AB` (8.2:1) |
| `--color-border` | `#DDDFD6` (decorative) | `#3C453C` |
| `--color-accent` | `#49685D` (white on it 6.1:1) | `#A6C3AD` (`#18251C` on it 8.4:1) |
| `--color-accent-hover` | `#3D594F` | `#B9D2BF` |
| `--color-accent-soft` | `#E7EEE8` | `#2D3D32` |

Additions, with reasons:

| Token | Light | Dark | Why |
|---|---|---|---|
| `--color-border-strong` | `#838B83` | `#76807A` | Input and button boundaries must reach 3:1 (WCAG 1.4.11); `#DDDFD6` is 1.3:1. |
| `--color-bg-hover` | `#E9E8E1` | `#313831` | Hover rows; secondary text still 4.55:1 / 5.7:1 on it. |
| `--color-bg-selected` | = accent soft | = accent soft | Selected source, pressed toggle. |
| `--color-bg-highlight` | `#E0EAE2` | `#364A3C` | Start of the cited-source flash. First try `#D6E3D9` dropped metadata to 4.2:1; the test caught it. |
| `--color-bg-disabled`, `--color-text-disabled` | `#ECEBE5`, `#7F877F` | `#262B26`, `#6F776F` | Disabled controls (exempt from contrast, kept readable). |
| Warning (insufficient evidence) | bg `#FBF2DC`, text `#6A4B0C` (7.2:1), icon `#8A6312` | bg `#2F2817`, text `#EED9A2` | Amber reads as "attention", distinct from error red. |
| Error | bg `#FAECE8`, text `#8E2E22` (7.1:1) | bg `#34201C`, text `#F3B9AE` | Technical failures. |
| Info | bg `#E9F0F2`, text `#2C5061` | bg `#1D2A30`, text `#B4D0DC` | Neutral notes (e.g. "checked, not enough to answer"). |
| `--color-bg-backdrop` | ink at 32% | black at 55% | Drawer backdrop. |

No success/green "verified" role on purpose (principle 4).

## Typography

Copernicus/Tiempos and StyreneB are licensed and not available to the project, so open-source
fonts are used. They are **not** claimed to match the Claude fonts. All are self-hosted through
Fontsource (SIL OFL 1.1), bundled by Vite (no font CDN), and include a Vietnamese subset; the
showcase checks with `document.fonts` that each face actually loads.

| Role | Font | Package | Fallback |
|---|---|---|---|
| Display (empty-state greeting, brand) | Newsreader (variable, optical size) | `@fontsource-variable/newsreader` | Georgia, serif |
| UI and answers | Inter (variable) | `@fontsource-variable/inter` | system-ui |
| Code, category codes | JetBrains Mono (variable) | `@fontsource-variable/jetbrains-mono` | ui-monospace |

Newsreader was chosen over Cormorant Garamond (the substitute named in DESIGN-claude.md): at
26–30px Cormorant is thin, with a small x-height and crowded Vietnamese stacked marks (ặ, ẫ, ữ).
The showcase shows both side by side; Cormorant is a dev-only dependency for that comparison.

| Token | Size / line-height | Use |
|---|---|---|
| `--text-display-*` | 30px / 1.2 (26px under 640px), weight 400, -0.01em | Empty-state greeting only |
| `--text-title-*` | 18px / 1.35 | Panel/section headings |
| `--text-answer-*` | 16px / 1.7 | Answer body |
| `--text-body-*` | 14px / 1.55 | UI, user turns, source titles |
| `--text-meta-*` | 13px / 1.45, secondary color | Metadata, hints |
| `--text-caption-*` | 12px / 1.4 | Labels (uppercase, +0.04em), badges, citation numbers |
| `--text-code-*` | 13px / 1.6, mono | Code blocks |

## Space, radius, elevation, motion, layout

- Space: `--space-1/2/3/4/6/8/12` = 4, 8, 12, 16, 24, 32, 48px.
- Radius: `sm` 6px (badges, citations, inline code), `md` 8px (buttons, inputs), `lg` 12px (callouts,
  sources, suggestion list), `xl` 16px (composer), `full`.
- Elevation: borders and surface color first. `--shadow-sm` on the composer and checked segment,
  `--shadow-md` on drawers. Nothing else casts a shadow.
- Motion: `fast` 120ms (hover), `base` 200ms (tooltip), `slow` 280ms (drawer), `highlight` 1600ms
  (cited-source flash). `prefers-reduced-motion: reduce` sets all to 0, stops the loading dots and
  hides the flash.
- Layout: sidebar 232px, header 56px, reading column 760px, sources 352px, drawer `min(92vw, 400px)`,
  gutter 24px (16px under 640px).
- Stacking: `--z-sticky` 10, `--z-overlay` 30, `--z-tooltip` 50. Drawers use the native dialog top layer.

Exceptions with a reason: the mono badge uses 11px (mono runs wider than sans); the tooltip uses
inverted text/canvas colors; 44px touch targets on `pointer: coarse`.
