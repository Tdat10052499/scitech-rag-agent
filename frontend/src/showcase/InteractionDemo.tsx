import { useState } from "react";
import { AssistantMessage, SourcePanel, UserMessage, citedIndices, findSource } from "../ui";
import type { ActiveCitation } from "../ui";
import { CONVERSATION, TURN_1, TURN_2 } from "./fixtures";
import { Section } from "./Example";

const TURNS = [TURN_1, TURN_2];

/** Two answers that both cite [1] for different papers: a click shows the right one, in its turn. */
export function InteractionDemo() {
  const [panelTurnId, setPanelTurnId] = useState(TURN_1.id);
  const [active, setActive] = useState<ActiveCitation | null>(null);
  const [log, setLog] = useState<string[]>([]);

  const turn = TURNS.find((t) => t.id === panelTurnId) ?? TURN_1;
  const number = TURNS.indexOf(turn) + 1;
  const question = CONVERSATION[CONVERSATION.indexOf(turn) - 1];

  function cite(turnId: string, index: number) {
    setPanelTurnId(turnId);
    setActive((prev) => ({ turnId, index, nonce: (prev?.nonce ?? 0) + 1 }));
    const s = findSource(TURNS, { turnId, index });
    const n = TURNS.findIndex((t) => t.id === turnId) + 1;
    setLog((l) => [`Answer ${n} · [${index + 1}] → ${s?.title ?? "missing"} (${s?.chunk_id ?? "-"})`, ...l].slice(0, 5));
  }

  return (
    <Section
      id="interaction"
      title="Interaction: citation → source"
      intro={
        <p>
          Click <strong>[1]</strong> in both answers: each opens a different paper, from its own answer. Only the sources list scrolls; the conversation keeps its
          position. Clicking the same number again replays the highlight.
        </p>
      }
    >
      <div className="sc-interaction">
        <div className="sc-interaction__conversation">
          {CONVERSATION.map((m) =>
            m.role === "user" ? (
              <UserMessage key={m.id} text={m.text} />
            ) : (
              <AssistantMessage
                key={m.id}
                turn={m}
                number={TURNS.indexOf(m) + 1}
                activeIndex={active?.turnId === m.id ? active.index : null}
                sourcesShown={panelTurnId === m.id}
                onCite={(i) => cite(m.id, i)}
                onShowSources={() => {
                  setPanelTurnId(m.id);
                  setActive(null);
                }}
              />
            ),
          )}
        </div>
        <div className="sc-interaction__side">
          <div className="sc-panel-frame sc-panel-frame--tall">
            <SourcePanel
              sources={turn.sources}
              turnLabel={`Answer ${number}`}
              question={question?.text}
              cited={citedIndices(turn.text)}
              active={active?.turnId === turn.id ? active : null}
            />
          </div>
          <div className="sc-event-log">
            <span className="ui-label">Citation log</span>
            {log.length === 0 ? <p>No citation clicked yet.</p> : <ol>{log.map((l, i) => <li key={i}>{l}</li>)}</ol>}
          </div>
        </div>
      </div>
    </Section>
  );
}
