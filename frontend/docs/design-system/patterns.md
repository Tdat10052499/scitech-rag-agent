# Interaction patterns, responsive behaviour, accessibility

Approved with the baseline on 2026-10-21 and implemented in the chat screen (`src/chat/ChatWorkspace.tsx`).

## Citations → sources

1. `[n]` refers to source `n` of the **same answer** (contract). Identify a citation by
   `(turn id, index)`; never by the number alone (`sourceKey`, `findSource` in `citations.ts`).
2. Click on an available marker → the page sets `{turnId, index, nonce}`, shows that answer's
   sources, opens the panel (drawer on small screens), and the panel scrolls **only its own list**
   to the source and highlights it (filled number, left bar, background, 1.6s flash). The
   conversation scroll position does not change. Verified in the browser: conversation `scrollTop`
   stayed at 120px while the panel scrolled to the item.
3. A second click on the same marker replays the flash (`nonce`).
4. The panel says which answer it belongs to ("Answer 2" + the question).
5. A number with no matching source is drawn dashed, not clickable, with screen-reader text
   "source n is not in the list for this answer". It is never pointed at another source.
6. Markers stay on one line with the word before and the punctuation after (`citeGroups.ts`);
   a line never starts with "." after a marker. (A word-joiner approach was tried and measured not to
   work in Chrome next to inline-block buttons.)
7. Sources the answer does not cite are marked "Retrieved, not cited in this answer"
   (derived from the text with `citedIndices`, only after `done`).
8. A screen-reader live region in the panel announces "Source 2 of 3: title".

## Sources

- Show only present fields: title (link only for http/https), kind, year (arXiv: first version;
  Wikipedia: "Revised YYYY"), arXiv id for arXiv records, categories (mono badges), snippet.
- Fallbacks: empty title → "Untitled source" (italic, secondary); no URL → "No link available";
  invalid date → no year. No score.
- Long snippets (>220 chars) start clamped to 3 lines with "Show full excerpt" (`aria-expanded`).
- Panel states: pending ("Looking for sources..."), failed, insufficient (with or without checked
  passages), ready.

## Composer

- Enter sends; Shift+Enter inserts a line break; nothing is sent while an IME composes
  (`isComposing` or keyCode 229, for Safari). Verified with real key events in the browser.
- Grows with the text up to 200px, then scrolls inside. Focus ring on the whole frame.
- `waiting` ("Searching the corpus...") and `streaming` ("Writing the answer..."): typing stays
  possible, sending waits. **No stop button**: the API has no cancel, and aborting the fetch would
  leave the server generating. Add one only with a backend change.
- Hint "Enter to send · Shift+Enter for a new line" is hidden under 640px.
- After sending, the new question scrolls to the top once; the view does not follow
  the streaming text, so a reader of an earlier answer is not pulled away.

## Insufficient evidence vs. error

| | Insufficient evidence | Technical error |
|---|---|---|
| Meaning | The request worked; the corpus had too little | Something failed |
| Signal | `done.insufficient_evidence: true` | `error` event or transport failure |
| Look | Warning callout, magnifier-minus icon, title "Not enough evidence in the corpus" | Error callout, alert icon, title per error code |
| Content | Explanation + rephrasing tips (approved copy) | Server message; "The answer stopped early" when text had arrived; "Try again" on the latest failed answer |

## Responsive

| Width | Layout |
|---|---|
| ≥ 1280px | Sidebar 232 · conversation (column ≤ 760) · sources 352 |
| 1024–1279px | Menu button opens the sidebar drawer; sources inline |
| < 1024px | Sidebar and sources are drawers; "Sources" button and citations open the sources drawer |
| < 640px | 16px gutters, display 26px, composer hint hidden |
| touch (`pointer: coarse`) | Icon buttons and medium buttons 44px; citation markers 24px |

Only code blocks scroll sideways; long words and URLs wrap. Checked: no horizontal page overflow
at 375px for the showcase and the specimen.

## Accessibility checklist

- Landmarks: `main`, sidebar `aside` "Workspace", sources `aside` "Sources", conversation
  `section` "Conversation"; each answer is an `article` named "Answer n".
- Icon buttons have `aria-label`; tooltips repeat it visually and are `aria-hidden`.
- Visible focus everywhere (`:focus-visible`, 2px ring, ≥ 3:1 on every surface).
- Drawers: native modal dialog; focus moves in, stays in, Escape and backdrop close, focus returns
  to the opener (verified: Escape returned focus to the citation button "Source 2: …").
- One polite live region for answer progress (`LiveStatus`) and one in the sources panel.
- States never rely on color alone.
- `prefers-reduced-motion`: durations 0, no flash, static dots, instant scrolling.
- Contrast: AA for every rendered pair in both themes (automated test).

## Conversation flow (chat screen)

- Follow-ups: shown under the latest answer that has some, so an error or insufficient answer does
  not hide them. A click (or an example question on the empty screen) fills the composer and
  focuses it; Enter sends.
- New conversation: aborts a running answer, clears the turns and the draft, starts a new
  `session_id`; the sources panel goes back to `idle`.
- Try again: only on the latest answer, only after an error, only when nothing is streaming. It
  removes the failed question and answer and sends the same question again in the same session (the
  agent keeps only successful turns in its history). Works for agent errors and for an unreachable
  server.
- A new answer shows its own sources in the panel; the panel list starts at the top for each answer.
- The draft lives in the screen state: switching theme, opening or closing sources or the sidebar,
  and crossing a breakpoint keep it.
