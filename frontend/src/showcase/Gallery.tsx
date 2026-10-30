import { useState } from "react";
import {
  AssistantMessage,
  Badge,
  Button,
  Callout,
  Drawer,
  EmptyConversationState,
  ErrorState,
  FollowUpSuggestions,
  IconButton,
  InsufficientEvidenceState,
  LoadingIndicator,
  MessageComposer,
  SourceItem,
  SourcePanel,
  Textarea,
  ThemeToggle,
  UserMessage,
} from "../ui";
import type { ComposerState, ThemePreference } from "../ui";
import { CloseIcon, MenuIcon, PanelRightIcon, PlusIcon } from "../ui/icons";
import {
  ERROR_AFTER_TEXT,
  ERROR_BEFORE_TEXT,
  INSUFFICIENT,
  LONG_QUESTION,
  MARKDOWN_SAMPLE,
  MISSING_CITATION,
  SEARCHING,
  SOURCES,
  STREAMING,
  TRANSPORT_ERROR,
  TURN_1,
} from "./fixtures";
import { EXAMPLE_QUESTIONS } from "../chat/ChatWorkspace";
import { Example, Grid, Section } from "./Example";

function Log({ text }: { text: string }) {
  return (
    <p className="sc-log" aria-live="polite">
      {text || "Interact with the example; the callback result appears here."}
    </p>
  );
}

function BasicComponents({ theme, onTheme }: { theme: ThemePreference; onTheme: (t: ThemePreference) => void }) {
  const [drawer, setDrawer] = useState<null | "left" | "right">(null);
  const [field, setField] = useState("");
  return (
    <Section id="basic" title="Basic components" intro={<p>Hover and keyboard focus (Tab) are live on every control; disabled states are shown next to the default.</p>}>
      <Grid min={320}>
        <Example title="Button" note="primary: one main action per area · secondary: bordered · ghost: quiet, in toolbars and rows">
          <div className="sc-row">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
          </div>
          <div className="sc-row">
            <Button variant="primary" disabled>
              Primary
            </Button>
            <Button variant="secondary" disabled>
              Secondary
            </Button>
            <Button variant="ghost" disabled>
              Ghost
            </Button>
          </div>
          <div className="sc-row">
            <Button variant="secondary" icon={<PlusIcon size={16} />}>
              New conversation
            </Button>
            <Button variant="ghost" size="sm" icon={<PanelRightIcon size={16} />}>
              Sources
            </Button>
            <Button variant="ghost" size="sm" className="is-selected" aria-pressed="true">
              Selected
            </Button>
          </div>
        </Example>

        <Example title="IconButton + Tooltip" note="Accessible name = tooltip text. Tooltip on hover (after 400ms) and on keyboard focus; Escape hides it. 44px targets on touch screens.">
          <div className="sc-row">
            <IconButton label="Open workspace menu" icon={<MenuIcon />} tooltip={{ align: "start" }} />
            <IconButton label="Close" icon={<CloseIcon />} variant="secondary" />
            <IconButton label="Send question" icon={<PlusIcon />} variant="primary" />
            <IconButton label="Send question (disabled)" icon={<PlusIcon />} variant="primary" disabled />
          </div>
        </Example>

        <Example title="Textarea (field)">
          <label className="sc-field-label" htmlFor="sc-field">
            Notes
          </label>
          <Textarea id="sc-field" value={field} onChange={(e) => setField(e.target.value)} placeholder="Grows with its content" autoResize maxHeight={120} />
          <Textarea aria-label="Disabled field" value="Disabled" disabled readOnly />
        </Example>

        <Example title="Badge" note="Metadata labels, not buttons. Mono for codes such as arXiv categories.">
          <div className="sc-row">
            <Badge mono>cs.CL</Badge>
            <Badge mono>cs.LG</Badge>
            <Badge>Neutral</Badge>
            <Badge tone="accent">Accent</Badge>
            <Badge tone="outline">Outline</Badge>
          </div>
        </Example>

        <Example title="LoadingIndicator" note="Always with words; the dots stop under reduced motion.">
          <div className="sc-stack">
            <LoadingIndicator label="Searching the corpus..." />
            <LoadingIndicator size="sm" label="Writing the answer..." />
          </div>
        </Example>

        <Example title="ThemeToggle" note="Native radio buttons (arrow keys). Auto follows the OS. This one controls the page.">
          <ThemeToggle value={theme} onChange={onTheme} />
          <ThemeToggle value={theme} onChange={onTheme} showLabels={false} />
        </Example>

        <Example title="Callout" note="Tone is also told by icon and title, never by color alone.">
          <div className="sc-stack">
            <Callout tone="info" title="Information">
              <p>Neutral note inside the reading flow.</p>
            </Callout>
            <Callout tone="warning" title="Warning">
              <p>Used by the insufficient-evidence state.</p>
            </Callout>
            <Callout tone="error" title="Error">
              <p>Used by technical failures.</p>
            </Callout>
          </div>
        </Example>

        <Example title="Drawer" note="Native modal dialog: focus moves in and stays in, Escape or a backdrop click closes, focus returns to the button.">
          <div className="sc-row">
            <Button onClick={() => setDrawer("left")}>Open left drawer</Button>
            <Button onClick={() => setDrawer("right")}>Open right drawer</Button>
          </div>
          <Drawer open={drawer !== null} side={drawer ?? "right"} title="Example drawer" showTitle onClose={() => setDrawer(null)}>
            <div className="sc-drawer-body">
              <p>Tab moves between these controls only; the page behind is inert.</p>
              <Button variant="primary" onClick={() => setDrawer(null)}>
                Close drawer
              </Button>
            </div>
          </Drawer>
        </Example>
      </Grid>
    </Section>
  );
}

function ResearchComponents() {
  const [log, setLog] = useState("");
  const [draft, setDraft] = useState("");
  const [composerState, setComposerState] = useState<ComposerState>("idle");
  const cite = (label: string) => (index: number) => setLog(`${label}: citation [${index + 1}] clicked (0-based index ${index}).`);

  return (
    <Section id="research" title="Research components" intro={<Log text={log} />}>
      <Grid min={340}>
        <Example title="UserMessage · short">
          <UserMessage text="What is retrieval-augmented generation?" />
        </Example>
        <Example title="UserMessage · long, line breaks, unbroken URL">
          <UserMessage text={LONG_QUESTION} />
        </Example>
      </Grid>

      <Example title="AssistantMessage · done, citations, follow-ups" note="Citations are buttons named “Source n: title”. The sources button selects this answer in the panel." wide>
        <AssistantMessage turn={TURN_1} number={1} onCite={cite("Answer 1")} onShowSources={() => setLog("Answer 1: show sources.")} onFollowup={(q) => setLog(`Follow-up chosen: ${q}`)} />
      </Example>
      <Grid min={340}>
        <Example title="AssistantMessage · searching (no event yet)">
          <AssistantMessage turn={SEARCHING} number={2} />
        </Example>
        <Example title="AssistantMessage · streaming" note="Sources arrived first; text grows; follow-ups wait for done.">
          <AssistantMessage turn={STREAMING} number={2} onCite={cite("Streaming")} onShowSources={() => undefined} />
        </Example>
        <Example title="AssistantMessage · citation outside the source list" note="[4] with 2 sources: dashed, not clickable, explained to screen readers. Never remapped.">
          <AssistantMessage turn={MISSING_CITATION} number={3} onCite={cite("Missing")} activeIndex={0} />
        </Example>
        <Example title="AssistantMessage · Markdown subset" note="Renderer from src/markdown.ts: lists, bold, italic, code. HTML stays text.">
          <AssistantMessage turn={MARKDOWN_SAMPLE} number={4} onCite={cite("Markdown")} />
        </Example>
        <Example title="AssistantMessage · insufficient evidence" note="An answer state (warning tone, search icon), separate from errors. Suggestions: approved copy.">
          <AssistantMessage turn={INSUFFICIENT} number={5} />
        </Example>
        <Example title="AssistantMessage · error before any text">
          <AssistantMessage turn={ERROR_BEFORE_TEXT} number={6} onRetry={() => setLog("Retry: the chat resends the same question (latest failed answer only).")} />
        </Example>
        <Example title="AssistantMessage · error after partial text" note="The text received so far stays.">
          <AssistantMessage turn={ERROR_AFTER_TEXT} number={7} onCite={cite("Partial")} />
        </Example>
        <Example title="ErrorState · server not reachable (no error code)">
          <ErrorState error={TRANSPORT_ERROR.error!} />
        </Example>
      </Grid>

      <h3 className="sc-subtitle">Sources</h3>
      <Grid min={340}>
        <Example title="SourceItem · arXiv, complete">
          <SourceItem source={SOURCES.rag} n={1} cited />
        </Example>
        <Example title="SourceItem · Wikipedia (date = revision)">
          <SourceItem source={SOURCES.wiki} n={3} cited />
        </Example>
        <Example title="SourceItem · active (from a citation)" note="Filled number + left bar + background; not color alone.">
          <SourceItem source={SOURCES.dpr} n={2} active cited />
        </Example>
        <Example title="SourceItem · retrieved, not cited">
          <SourceItem source={SOURCES.selfRag} n={2} cited={false} />
        </Example>
        <Example title="SourceItem · long title, long excerpt, many categories">
          <SourceItem source={SOURCES.longTitle} n={3} />
        </Example>
        <Example title="SourceItem · only required fields (no link)">
          <SourceItem source={SOURCES.bare} n={4} />
        </Example>
        <Example title="SourceItem · empty title">
          <SourceItem source={SOURCES.untitled} n={5} />
        </Example>
        <Example title="SourceItem · unsafe URL and invalid date" note="A javascript: URL is not linked; the impossible date 2021-02-30 shows no year.">
          <SourceItem source={SOURCES.unsafeLink} n={6} />
        </Example>
      </Grid>

      <Grid min={300}>
        <Example title="SourcePanel · idle (no answer yet)">
          <div className="sc-panel-frame">
            <SourcePanel sources={[]} state="idle" />
          </div>
        </Example>
        <Example title="SourcePanel · pending">
          <div className="sc-panel-frame">
            <SourcePanel sources={[]} state="pending" turnLabel="Answer 2" question="Does giving the model more retrieved passages always help?" />
          </div>
        </Example>
        <Example title="SourcePanel · insufficient, no sources">
          <div className="sc-panel-frame">
            <SourcePanel sources={[]} insufficientEvidence turnLabel="Answer 5" />
          </div>
        </Example>
        <Example title="SourcePanel · insufficient, with checked passages">
          <div className="sc-panel-frame">
            <SourcePanel sources={[SOURCES.bare, SOURCES.untitled]} insufficientEvidence turnLabel="Answer 5" cited={new Set()} />
          </div>
        </Example>
        <Example title="SourcePanel · failed">
          <div className="sc-panel-frame">
            <SourcePanel sources={[]} state="failed" turnLabel="Answer 6" onClose={() => setLog("Close sources.")} />
          </div>
        </Example>
      </Grid>

      <h3 className="sc-subtitle">Input and suggestions</h3>
      <Grid min={340}>
        <Example title="MessageComposer · interactive" note="Enter sends · Shift+Enter new line · no send during IME composition · grows to 200px then scrolls.">
          <MessageComposer
            value={draft}
            onChange={setDraft}
            state={composerState}
            onSubmit={(t) => {
              setLog(`Submitted: “${t}”`);
              setDraft("");
              setComposerState("waiting");
              window.setTimeout(() => setComposerState("streaming"), 900);
              window.setTimeout(() => setComposerState("idle"), 2400);
            }}
          />
        </Example>
        <Example title="MessageComposer · waiting and streaming" note="Typing stays possible; sending waits. No stop button (not supported by the app).">
          <div className="sc-stack">
            <MessageComposer value="" onChange={() => undefined} onSubmit={() => undefined} state="waiting" />
            <MessageComposer value="A follow-up typed while the answer streams" onChange={() => undefined} onSubmit={() => undefined} state="streaming" />
          </div>
        </Example>
        <Example title="FollowUpSuggestions" note="Max 4 (API). The page decides whether a click fills the composer or sends.">
          <FollowUpSuggestions questions={TURN_1.followups} onSelect={(q) => setLog(`Follow-up chosen: ${q}`)} />
        </Example>
        <Example title="InsufficientEvidenceState (standalone)">
          <InsufficientEvidenceState />
        </Example>
      </Grid>
      <Example title="EmptyConversationState" note="The only place the display serif appears at size. Example questions are the ones the chat screen uses (src/chat/ChatWorkspace.tsx)." wide>
        <EmptyConversationState examples={EXAMPLE_QUESTIONS} onSelectExample={(q) => setLog(`Example chosen: ${q}`)} />
      </Example>
    </Section>
  );
}

export function Gallery({ theme, onTheme }: { theme: ThemePreference; onTheme: (t: ThemePreference) => void }) {
  return (
    <>
      <BasicComponents theme={theme} onTheme={onTheme} />
      <ResearchComponents />
    </>
  );
}
