# Components

All in `frontend/src/ui/`, exported from `src/ui/index.ts`. Presentational: they take data and
callbacks, never call the API. Data types come from `src/types.ts` (contract 0.2.1). Every component
below is shown in the showcase with the states listed; states not listed do not apply.

Load once per page:

```tsx
import "./ui/fonts";
import "./ui/styles.css";
```

## Basic

| Component | Variants / props | States |
|---|---|---|
| `Button` | `variant`: `primary` (one main action per area), `secondary` (bordered), `ghost` (toolbars, rows); `size`: `sm`, `md`; `icon` | hover, focus-visible, disabled, `is-selected` (ghost toggles with `aria-pressed`) |
| `IconButton` | `label` (required: accessible name and tooltip), `icon`, `variant`, `size`, `tooltip` (`false` or placement/align) | hover, focus-visible, disabled; 44px on touch |
| `Tooltip` | `content`, `placement`, `align`, `delay` | Shows on hover (400ms) and keyboard focus, Escape hides. Visual only (`aria-hidden`); the control must already have the same name |
| `Textarea` | `variant`: `field`, `bare`; `autoResize`, `maxHeight` | focus, disabled, grows then scrolls |
| `Badge` | `tone`: `neutral`, `accent`, `outline`; `mono` | static |
| `Callout` | `tone`: `info`, `warning`, `error`; `title` (required), `icon`, `actions` | static; not a live region |
| `LoadingIndicator` | `label` (required, visible), `size` | dots pulse; static under reduced motion |
| `LiveStatus` | `message` | one polite live region per page |
| `ThemeToggle` | `value`, `onChange`, `showLabels` | native radios: arrow keys, focus ring |
| `Drawer` | `open`, `onClose`, `side`, `title`, `showTitle`, `initialFocus` | native `<dialog>`: focus in and trapped, Escape and backdrop close, focus returns to opener, page scroll locked |

## Research

| Component | Props | States |
|---|---|---|
| `UserMessage` | `text`, `id?` | short, long, line breaks, unbroken URL |
| `AssistantMessage` | `turn` (`AssistantMessage` from `types.ts`), `number`, `activeIndex`, `sourcesShown`, `onCite(index, el)`, `onShowSources(el)`, `onRetry?`, `onFollowup?` (latest answer only) | `searching`, `answering` (streaming), `done`, `error` (with or without partial text), `insufficientEvidence`; citations available / active / missing |
| `CitationMarker` | `n`, `sourceTitle?` (absent = missing), `active`, `onActivate(el)` | available (button "Source n: title"), active (`aria-current`), missing (dashed, not interactive, explained to screen readers) |
| `SourceItem` | `source`, `n`, `active`, `flashKey`, `cited?`, `id?` | complete, Wikipedia (date = revision), long title/snippet ("Show full excerpt"), no link, empty title, unsafe URL, active, retrieved-not-cited |
| `SourcePanel` | `sources` (of one answer), `turnLabel`, `question`, `state` (`idle`/`ready`/`pending`/`failed`), `insufficientEvidence`, `cited`, `active` (`{index, nonce}`), `onClose?` | idle (no answer yet), pending, failed, insufficient without/with sources, ready, active source |
| `FollowUpSuggestions` | `questions` (max 4 shown), `onSelect`, `title` | list of rows; empty list renders nothing |
| `MessageComposer` | `value`, `onChange`, `onSubmit(trimmed)`, `state` (`idle`/`waiting`/`streaming`), `label`, `placeholder`, `showHint`, `textareaRef` | idle, empty (send disabled), waiting, streaming (typing allowed, sending waits), focus |
| `InsufficientEvidenceState` | `title`, `children`, `suggestions` (default: approved copy; `[]` hides) | static |
| `EmptyConversationState` | `title`, `description`, `examples`, `onSelectExample` | with/without examples |
| `ErrorState` | `error` (`ChatError`), `partial`, `onRetry?` | per code (`llm_unavailable`, `retrieval_failed`, `timeout`, `internal`, transport without code), partial |

## Layout

| Component | Props | Behaviour |
|---|---|---|
| `WorkspaceShell` | `sidebar`, `header`, `composer`, `sources`, `sourcesOpen` + `onSourcesOpenChange` (controlled), children | ≥1280px: three columns; 1024–1279px: sidebar drawer; <1024px: sidebar and sources drawers. Columns scroll separately; composer is below the conversation. Provides `useWorkspace()` |
| `Sidebar` / `SidebarSection` | `productName`, `onNewConversation`, `newConversationDisabled`, sections, `footer` | Only real content: there is no conversation history |
| `ConversationHeader` | `title`, `sourcesCount`, `onNewConversation`, `actions` | Inside the shell adds the menu button (drawer mode), "New conversation" when the sidebar is hidden, and the Sources toggle (`aria-expanded`, `aria-controls`) |
| `ReadingColumn` | `label`, children | Centered, max 760px + gutters |

## Logic and hooks (tested with `npm test`)

| Module | What it does | Tests |
|---|---|---|
| `citations.ts` | `resolveCitation`, `findSource`, `sourceKey`, `citedIndices` | multi-turn `[1]`, out-of-range, cites in code are ignored |
| `../citeGroups.ts` | keeps a marker on one line with the word before and the punctuation after | grouping, URLs not glued, text unchanged |
| `sourceMeta.ts` | `describeSource`, `safeHref` | missing/invalid dates, Wikipedia revision, empty title, `javascript:` URLs |
| `composerKeys.ts` | `shouldSubmitOnKey` | Enter, Shift+Enter, IME (`isComposing`, keyCode 229) |
| `contrast.ts` | WCAG ratio, `CONTRAST_PAIRS` | every pair, both themes, from the real `tokens.css` |
| `theme.ts`, `useMediaQuery.ts` | theme preference, media queries, `BREAKPOINTS` | in the showcase |

## Example: one answer with its sources

```tsx
const [active, setActive] = useState<ActiveCitation | null>(null);

<AssistantMessage
  turn={turn}
  number={2}
  activeIndex={active?.turnId === turn.id ? active.index : null}
  onCite={(index) => setActive((p) => ({ turnId: turn.id, index, nonce: (p?.nonce ?? 0) + 1 }))}
  onShowSources={() => setActive(null)}
/>
<SourcePanel
  sources={turn.sources}
  turnLabel="Answer 2"
  cited={turn.status === "done" ? citedIndices(turn.text) : undefined}
  active={active?.turnId === turn.id ? active : null}
/>
```

## The screen: `src/chat/`

| Module | Role |
|---|---|
| `ChatWorkspace.tsx` | The whole workspace screen from the components above: panel turn, active citation, draft, sidebar, empty state, scroll on send, live status. Rendered by the app **and** by the showcase specimen |
| `chatState.ts` | Pure rules: `ChatController` (what a screen needs from a conversation), `applyEvent`, `phaseOf`, `retryPlan`, `liveStatus`. Tested in `chatState.test.ts` |
| `useChat.ts` | Real conversation: `streamChat` (POST `/chat`), `session_id`, abort on new conversation or unmount, retry |
| `../showcase/useSimulatedChat.ts` | Showcase only: plays fixtures as the same events through the same `applyEvent` |

```tsx
// src/App.tsx
export default function App() {
  return <ChatWorkspace chat={useChat()} />;
}
```

`AnswerMarkdown` (`src/AnswerMarkdown.tsx`) takes `text` and `renderCite`; it is used only through
`AssistantMessage`.
