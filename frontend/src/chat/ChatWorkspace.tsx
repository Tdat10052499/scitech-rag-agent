import { useEffect, useRef, useState } from "react";
import type { AssistantMessage as AssistantTurn } from "../types";
import {
  AssistantMessage,
  BackendStatus,
  ConversationHeader,
  EmptyConversationState,
  LiveStatus,
  MessageComposer,
  ReadingColumn,
  Sidebar,
  SidebarSection,
  SourcePanel,
  ThemeToggle,
  UserMessage,
  WorkspaceShell,
  citedIndices,
  useThemePreference,
} from "../ui";
import type { ActiveCitation, ThemePreference } from "../ui";
import { BREAKPOINTS, prefersReducedMotion } from "../ui/useMediaQuery";
import { healthLabel } from "../health";
import { lastAnswer, liveStatus } from "./chatState";
import type { ChatController } from "./chatState";

// The research workspace screen, built only from design-system components (approved baseline,
// frontend/docs/design-system/). The app passes the real conversation (useChat); the showcase's layout
// specimen passes a simulated one. Both render exactly this component.

export const EXAMPLE_QUESTIONS = [
  "What is retrieval-augmented generation?",
  "How are LLM hallucinations detected?",
  "Does giving a model more retrieved passages always help?",
];

type Props = {
  chat: ChatController;
  initialTheme?: ThemePreference; // the showcase frame passes ?theme=
};

export function ChatWorkspace({ chat, initialTheme }: Props) {
  const { messages, phase } = chat;
  const [theme, setTheme] = useThemePreference(initialTheme);
  const [draft, setDraft] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [panelTurnId, setPanelTurnId] = useState<string | null>(null);
  const [active, setActive] = useState<ActiveCitation | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(() => window.matchMedia(`(min-width: ${BREAKPOINTS.sourcesInline}px)`).matches);

  const turns = messages.filter((m): m is AssistantTurn => m.role === "assistant");
  const latest = lastAnswer(messages);
  const panelTurn = turns.find((t) => t.id === panelTurnId);
  // Follow-ups belong to the latest answer that offers some (as before: an error or an
  // insufficient-evidence answer does not hide the previous suggestions).
  const followupOwner = [...turns].reverse().find((t) => t.followups.length > 0);

  // A new answer (or a new conversation) shows its own sources; a citation chosen earlier is cleared.
  const latestId = turns[turns.length - 1]?.id ?? null;
  useEffect(() => {
    setPanelTurnId(latestId);
    setActive(null);
  }, [latestId]);

  // When the user sends, bring the new question into view once. The view does not follow the
  // streaming text, so someone reading an earlier answer is not pulled away.
  const lastUserId = [...messages].reverse().find((m) => m.role === "user")?.id;
  const firstUserId = useRef(lastUserId);
  useEffect(() => {
    if (!lastUserId || lastUserId === firstUserId.current) return;
    document.getElementById(`turn-${lastUserId}`)?.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [lastUserId]);

  const questionOf = (turnId: string) => {
    const q = messages[messages.findIndex((m) => m.id === turnId) - 1];
    return q?.role === "user" ? q.text : undefined;
  };

  function cite(turnId: string, index: number) {
    setPanelTurnId(turnId);
    setActive((prev) => ({ turnId, index, nonce: (prev?.nonce ?? 0) + 1 }));
    setSourcesOpen(true);
  }

  function showSources(turnId: string) {
    setPanelTurnId(turnId);
    setActive(null);
    setSourcesOpen(true);
  }

  function chooseQuestion(q: string) {
    setDraft(q);
    textarea.current?.focus();
  }

  // A follow-up suggestion is sent at once as the next question of the same conversation. The draft
  // in the composer is kept. While another answer is being written the suggestions are disabled.
  function sendFollowup(q: string) {
    if (phase !== "idle") return;
    chat.send(q);
  }

  function newConversation() {
    chat.newConversation();
    setDraft("");
  }

  const firstQuestion = messages.find((m) => m.role === "user")?.text;

  return (
    <WorkspaceShell
      sourcesOpen={sourcesOpen}
      onSourcesOpenChange={setSourcesOpen}
      sourcesLabel="Sources"
      sidebar={
        <Sidebar onNewConversation={newConversation} newConversationDisabled={messages.length === 0} footer={<ThemeToggle value={theme} onChange={setTheme} />}>
          <SidebarSection title="Corpus">
            <p>LLM and NLP research papers from arXiv (cs.CL): titles and abstracts.</p>
          </SidebarSection>
          <SidebarSection title="How answers work">
            <p>Answers use only retrieved passages. Each number such as [1] opens its source.</p>
          </SidebarSection>
        </Sidebar>
      }
      header={
        <ConversationHeader
          title={firstQuestion ?? "New conversation"}
          sourcesCount={panelTurn?.sources.length}
          onNewConversation={newConversation}
          newConversationDisabled={messages.length === 0}
          actions={chat.health && <BackendStatus state={chat.health.kind} label={healthLabel(chat.health)} />}
        />
      }
      composer={<MessageComposer value={draft} onChange={setDraft} onSubmit={(t) => (chat.send(t), setDraft(""))} state={phase} textareaRef={textarea} />}
      sources={
        panelTurn ? (
          <SourcePanel
            key={panelTurn.id} // another answer starts at the top of its list
            sources={panelTurn.sources}
            turnLabel={`Answer ${turns.indexOf(panelTurn) + 1}`}
            question={questionOf(panelTurn.id)}
            state={panelTurn.status === "searching" ? "pending" : panelTurn.status === "error" && panelTurn.sources.length === 0 ? "failed" : "ready"}
            insufficientEvidence={panelTurn.insufficientEvidence}
            cited={panelTurn.status === "done" ? citedIndices(panelTurn.text) : undefined}
            active={active?.turnId === panelTurn.id ? active : null}
            onClose={() => setSourcesOpen(false)}
          />
        ) : (
          <SourcePanel sources={[]} state="idle" onClose={() => setSourcesOpen(false)} />
        )
      }
    >
      <ReadingColumn>
        {messages.length === 0 && <EmptyConversationState examples={EXAMPLE_QUESTIONS} onSelectExample={chooseQuestion} />}
        {messages.map((m) => {
          if (m.role === "user") return <UserMessage key={m.id} id={`turn-${m.id}`} text={m.text} />;
          const isLatest = m === latest;
          return (
            <AssistantMessage
              key={m.id}
              turn={m}
              number={turns.indexOf(m) + 1}
              activeIndex={active?.turnId === m.id ? active.index : null}
              sourcesShown={sourcesOpen && panelTurnId === m.id}
              onCite={(index) => cite(m.id, index)}
              onShowSources={() => showSources(m.id)}
              onRetry={isLatest && m.status === "error" && phase === "idle" ? chat.retry : undefined}
              onFollowup={m === followupOwner ? sendFollowup : undefined}
              followupDisabled={phase !== "idle"}
            />
          );
        })}
      </ReadingColumn>
      <LiveStatus message={liveStatus(messages)} />
    </WorkspaceShell>
  );
}
