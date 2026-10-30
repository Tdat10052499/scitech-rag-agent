# Approval, integration and open points

Status: **APPROVED BASELINE (2026-10-21, LDN)** — the showcase as reviewed that day. The chat screen
uses it since the same day (`src/App.tsx` → `src/chat/ChatWorkspace.tsx`).

## Decisions settled by the approval

The review questions of the draft were settled by approving the showcase as shown:

| # | Topic | Settled as |
|---|---|---|
| 1 | Palette | Starting palette + additions in `foundations.md` |
| 2 | Fonts | Newsreader (display), Inter (UI, answers), JetBrains Mono (code) |
| 3 | Citation look | Number chips without brackets; filled when active; dashed when missing |
| 4 | Turns | Answer on the page, question in a light block |
| 5 | Uncited sources | Marked "Retrieved, not cited in this answer" |
| 6 | Follow-ups | Full-width list; a click **fills the composer** and focuses it (as in the specimen and the previous app); the user sends with Enter |
| 7 | Sidebar | Product name, New conversation, corpus facts, theme switch |
| 8 | Breakpoints | 1280 / 1024 / 640px |
| 9 | Copy | As shown, with the corpus correction below |
| 10 | Try again | Implemented: resends the question of the latest failed answer (see `patterns.md`) |
| 11 | Backend badge | Removed from the product; the unreachable-server error state covers it |
| 12 | Auto-scroll | On send the new question scrolls into view once; the stream is not followed |

## Changes after approval

Made while integrating; none changes a color, font, size, radius, icon, layout or motion token.

| Change | Why |
|---|---|
| Corpus sentence (sidebar, insufficient-evidence tips, empty-state description) no longer mentions Wikipedia | ADR 0003: Wikipedia was cut from v1.0, so the sentence would be false in the product |
| `SourcePanel` gained `state="idle"` ("The sources of each answer appear here…") | Before the first answer the panel said "No sources for this answer", which is wrong when there is no answer; shown in the showcase |
| `AnswerMarkdown` takes `renderCite` (required); its old plain `[n]` button is gone | The old chat screen that used it was replaced; one rendering path |
| Follow-ups are shown on the latest answer that has some | Keeps the previous app's behaviour: an error or insufficient answer does not hide the last suggestions |
| Choosing a follow-up or example also focuses the composer | So Enter sends it; the text is the same as before |
| The specimen's wiring moved to `src/chat/ChatWorkspace.tsx`; the specimen now renders that component with `useSimulatedChat` | App and showcase must not drift apart |

## Known limits

- Checked in the Claude desktop app's built-in Chromium browser (1440px, 1100px, 610px, 375px; light
  and dark). Not checked in Firefox or Safari, nor with a real screen reader.
- End to end only against the repo's offline demo agent (`make run` backend); the real index and LLM
  are not wired into `/chat` yet, so real answer lengths and source counts were exercised with a
  hand-made SSE stream through the real client instead.
- `light-dark()` needs Chrome/Edge 123+, Firefox 120+, Safari 17.5+.
- `Tooltip` is positioned with CSS only: it can be clipped inside a scrolling container near an edge.
- Bundle: JS 79.3 kB gzip (was 72.7), CSS 8.6 kB gzip (was 1.9); fonts are separate files, and the
  browser downloads only the subsets a page uses.
- The sources panel open/closed state is kept when the window crosses a breakpoint (closing the
  drawer on a narrow window leaves the inline panel closed on a wide one until "Sources" is pressed).

## Still open

- Rating buttons (`message_id`, Week 6) and a stop button (needs a backend cancel) are not designed.
