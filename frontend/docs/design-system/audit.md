# Audit of the frontend (2026-10-21)

> Historical: the state **before** the design system. Since the integration on 2026-10-21 the
> chat screen is `src/chat/ChatWorkspace.tsx`; `MessageList.tsx`, `SourcesPanel.tsx`, `StatusBadge.tsx`,
> `App.css` and `chat.css` were removed. See [review.md](review.md).

Baseline: branch `feat/w3-d2-ldn-1-sources-markdown` (PR #83, open at the time; merged on 2026-10-21), which was `main` at `eb0031c`
plus the Markdown renderer. The design system was built on it and later moved onto `main` as `feat/w6-d1-ldn-1-ui-polish`.
Claims below point to files on that baseline. No `.env` or credential was read.

## Stack and tooling

| Topic | Finding | Evidence |
|---|---|---|
| Framework | React 19 + Vite 8 + TypeScript 7, static SPA, Node 22 | `frontend/package.json`, ADR 0004 |
| Package manager | npm with `package-lock.json`; `npm ci` | `frontend/README.md` |
| Scripts | `dev`, `build` (`tsc -b && vite build`), `typecheck`, `test` (Node's built-in runner with `--experimental-strip-types`), `preview` | `frontend/package.json` |
| CI | `npm ci`, `typecheck`, `test`, `build` | `.github/workflows/ci.yml` on `main` |
| Styling | Plain CSS with a few custom properties (`--bg`, `--accent` blue `#2557d6`), dark mode only through `prefers-color-scheme`, no toggle | `frontend/src/App.css` |
| Fonts | `system-ui` only; nothing loaded | `frontend/src/App.css` |
| Icons | None | — |
| Component library / showcase | None. ADR 0004 planned Tailwind, shadcn/ui, react-markdown and openapi-typescript; none is installed | ADR 0004 "Decision", `package.json` |
| API types | Hand-written in `src/types.ts` (contract 0.2.1), not generated | `frontend/src/types.ts` |
| Tests | SSE client (`api.test.ts`) and Markdown parser (`markdown.test.ts`); screens checked by hand | `frontend/README.md` |

Found during the audit: on Windows (case-insensitive file system) `npm run typecheck` and
`npm run build` failed on the PR #83 baseline, because `./Markdown` resolved to `markdown.ts`
instead of `Markdown.tsx`. Fixed by renaming the component to `AnswerMarkdown.tsx`, pushed to PR #83
as `15339cd` and merged with it on 2026-10-21.

## Product features: implemented, documented only, missing

| Feature (as described) | Status | Evidence |
|---|---|---|
| Ask a question | Implemented, single-line `<input>`; Enter submits; no multi-line | `src/App.tsx` (form `composer`) |
| Answer with `[n]` citations | Implemented. `[n]` is a button when `1 <= n <= sources.length`, otherwise plain text. Mapping is per answer, as in the contract | `src/AnswerMarkdown.tsx`, `api.openapi.yaml` (`/chat` description) |
| Streaming | Implemented: `fetch` + SSE parser; statuses `searching`, `answering`, `done`, `error` | `src/api.ts`, `src/App.tsx` (`applyEvent`) |
| Sources next to the answer | Implemented: one panel, shows the sources of the selected answer; a citation selects and scrolls to the source | `src/SourcesPanel.tsx`, `src/App.tsx` (`cite`) |
| Source title, year, category, link | Implemented: title (link if `url`), kind (`arxiv`/`wikipedia`/`openalex`), year from `published_at`, arXiv categories, snippet. Score hidden on purpose (PR #83) | `src/SourcesPanel.tsx` |
| Follow-up questions | Implemented, max 4; a click **fills the input**, it does not send | `src/MessageList.tsx`, `App.tsx` (`onFollowup={setDraft}`) |
| New conversation | Implemented: aborts the stream, new `session_id` | `src/App.tsx` (`newConversation`) |
| "Not enough evidence" | Implemented: `done.insufficient_evidence` → badge "Not enough evidence in the corpus"; sources panel explains | `src/MessageList.tsx`, `src/SourcesPanel.tsx` |
| Technical error state | Implemented: `error` event codes and transport errors | `src/api.ts` (`ChatTransportError`), `MessageList.tsx` |
| Answer Markdown | Implemented in PR #83 (own parser, no `innerHTML`) | `src/markdown.ts`, `src/AnswerMarkdown.tsx` |
| Backend status in the header | Implemented ("Backend: ok") — internal technical info shown as product content | `src/StatusBadge.tsx` |
| Light/dark | Partly: automatic dark palette, no user choice | `src/App.css` |
| Follow-up click sends at once | Documented only (plan W4-D3-LDN-1) | `docs/plan/week-04.md` |
| Stop button | Documented as optional ("if the framework allows"); not implemented; the server cannot be told to stop | `docs/plan/week-04.md` |
| Rating / feedback (`message_id`) | Documented only (Week 6) | `api.openapi.yaml` (`Done.message_id`) |
| Retry after an error | Not implemented | — |
| PDF upload, model choice, login, library, export, history | Not present, out of scope (brief: no accounts) | `docs/00-project-brief.md` |

## Data shapes the UI must respect

- `Source`: required `chunk_id`, `doc_id`, `title`, `score`; optional `url`, `snippet`, `source`,
  `published_at` (arXiv: first version; Wikipedia: **revision** date), `categories`.
- Event order: `sources` (once, first, may be empty) → `token`* → `followups`? → `done` | `error`.
- `[n]` = n-th element (1-based) of the `sources` of the **same** response. Two answers can both
  cite `[1]` and mean different papers.
- Answers are plain text from a small model (llama3.2:3b, ADR 0006); PR #83 measured almost no
  Markdown in 30 real answers.
