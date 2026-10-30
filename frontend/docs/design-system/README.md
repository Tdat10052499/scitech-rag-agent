# SciTech RAG design system

> **Status: APPROVED BASELINE (2026-10-21, LDN).** The showcase as reviewed on 2026-10-21 was
> approved as the design baseline and the chat screen now uses it. Rule 8 below applies from now on:
> changes to base colors, fonts, spacing scale, radii, icons, layout, motion or component props are
> proposed first. Changes made while integrating are listed in [review.md](review.md#changes-after-approval).

A small design system and UI kit for the research workspace: tokens (light and dark), fonts,
reusable React components and a showcase. It lives in `frontend/src/ui/`; the showcase in
`frontend/src/showcase/` and `frontend/showcase.html` (dev server only, not in `npm run build`).
The chat screen (`src/App.tsx`) and the showcase's layout specimen render the **same**
`src/chat/ChatWorkspace.tsx`; only the data source differs (`useChat`: real `/chat` API;
`useSimulatedChat`: fixtures, showcase only).

## What the approved baseline consists of

| Part | Files |
|---|---|
| Tokens and theme | `src/ui/tokens.css` (primitive, semantic, component layers; `light-dark()`), `src/ui/theme.ts` |
| Fonts | `src/ui/fonts.ts`: Newsreader (display), Inter (UI, answers), JetBrains Mono (code) |
| Base and component styles | `src/ui/base.css`, `components.css`, `research.css`, `layout.css`, `styles.css` |
| Icons | `src/ui/icons.tsx` |
| Components | every `src/ui/*.tsx` exported from `src/ui/index.ts` |
| Behaviour helpers | `src/ui/citations.ts`, `sourceMeta.ts`, `composerKeys.ts`, `contrast.ts`, `useMediaQuery.ts`, `src/citeGroups.ts` |
| Showcase | `showcase.html`, `src/showcase/*` |
| Layout choices | sidebar 232 · reading column ≤ 760 · sources 352; breakpoints 1280 / 1024 / 640px; drawers below them |
| Behaviour shown in the specimen | follow-up click fills the composer; the new question scrolls into view once on send, the stream is not followed; no backend status badge; sidebar = product name, New conversation, corpus facts, theme switch |

| Document | Content |
|---|---|
| [audit.md](audit.md) | What the frontend had on 2026-10-21, with file evidence |
| [foundations.md](foundations.md) | Principles, tokens, theme, color and contrast, typography and fonts |
| [components.md](components.md) | Component inventory, props, variants, states, examples |
| [patterns.md](patterns.md) | Citations and sources, composer, states, responsive, accessibility |
| [review.md](review.md) | Points to review, known limits, integration plan |

## Open the showcase

```bash
cd frontend
npm ci
npm run showcase      # opens http://localhost:5173/showcase.html
```

No backend or API key is needed: all data is illustrative fixtures (`src/showcase/fixtures.ts`).
Sections: color (live values and contrast in both themes), typography (font check, Vietnamese),
spacing/radius/elevation/motion, basic components, research components, the citation interaction
across two answers, and a layout specimen in a resizable frame (phone 390 → wide 1440).
The specimen alone: `http://localhost:5173/showcase.html?view=specimen` (add `&theme=dark`,
`&start=empty`).

Checks: `npm run typecheck`, `npm test` (includes citation mapping, source metadata, composer keys
and a WCAG contrast test over `tokens.css`), `npm run build`.

## Files

```
frontend/
  showcase.html                 showcase entry (dev only)
  src/ui/
    tokens.css                  primitive → semantic → component tokens, light-dark()
    base.css  components.css  research.css  layout.css  styles.css (imports all)
    fonts.ts                    self-hosted fonts (Fontsource, OFL)
    *.tsx                       components (see components.md)
    citations.ts  sourceMeta.ts  composerKeys.ts  contrast.ts  theme.ts  useMediaQuery.ts
    *.test.ts                   behaviour tests
  src/citeGroups.ts             keeps citation markers with neighbouring text (used by AnswerMarkdown)
  src/showcase/                 showcase page, layout specimen, fixtures
```

## Rules for developers and AI agents

1. Read this folder before changing any UI.
2. Look for an existing component in `src/ui/index.ts` before creating one.
3. Use semantic tokens (`--color-*`, `--space-*`, …) only; no hex values or ad-hoc sizes in
   components or screens. Primitives are for `tokens.css` only.
4. Do not copy a component to change its color or spacing; add a variant or a prop.
5. Do not change a global token to fix one local case.
6. A new variant needs a real use case, an example in the showcase and a line in `components.md`.
7. An approved change updates code, showcase and docs in the same PR.
8. After the baseline is approved, changes to base colors, fonts, the spacing scale or a component's
   props must be proposed (issue or PR description) before they are applied.
9. Answers stay rendered through `src/markdown.ts` + `src/AnswerMarkdown.tsx` (React elements,
   never `innerHTML`). Links only for http(s) (`safeHref`).
10. Never show a confidence %, a "verified" label or the retrieval score without data that
    supports it; never invent missing metadata.
11. Keep `npm test` green: the contrast test fails if a token change breaks WCAG AA.
