import { useEffect, useId, useRef, useState } from "react";
import type { Source } from "../types";
import { Callout } from "./Callout";
import { CloseIcon } from "./icons";
import { IconButton } from "./IconButton";
import { LoadingIndicator } from "./LoadingIndicator";
import { SourceItem } from "./SourceItem";
import { describeSource } from "./sourceMeta";
import { prefersReducedMotion } from "./useMediaQuery";

type Props = {
  sources: Source[]; // the `sources` of ONE answer, in the order the API sent them
  turnLabel?: string; // which answer these belong to, e.g. "Answer 2"
  question?: string; // the question that answer responds to
  // idle: no answer yet; pending: request sent, no `sources` event yet; failed: the stream failed first
  state?: "idle" | "ready" | "pending" | "failed";
  insufficientEvidence?: boolean;
  cited?: Set<number>; // 0-based indices the answer cites; omit while unknown
  active?: { index: number; nonce: number } | null; // the source to bring into view and highlight
  onClose?: () => void; // shows a close button (drawer, or a collapsible inline panel)
};

/**
 * The sources of one answer. A citation click scrolls only this panel's own list (never the page or
 * the conversation, so the reading position is kept) and highlights the source.
 */
export function SourcePanel({ sources, turnLabel, question, state = "ready", insufficientEvidence = false, cited, active, onClose }: Props) {
  const headingId = useId();
  const idBase = useId();
  const body = useRef<HTMLDivElement>(null);
  const [announcement, setAnnouncement] = useState("");

  const activeIndex = active?.index;
  const nonce = active?.nonce;
  useEffect(() => {
    if (activeIndex === undefined) return;
    const container = body.current;
    const item = container?.querySelector<HTMLElement>(`[data-source-index="${activeIndex}"]`);
    const source = sources[activeIndex];
    if (!container || !item || !source) return;
    const c = container.getBoundingClientRect();
    const r = item.getBoundingClientRect();
    if (r.top < c.top || r.bottom > c.bottom) {
      const margin = 12;
      container.scrollTo({
        top: container.scrollTop + (r.top - c.top) - margin,
        behavior: prefersReducedMotion() ? "auto" : "smooth",
      });
    }
    setAnnouncement(`Source ${activeIndex + 1} of ${sources.length}: ${describeSource(source).title}`);
  }, [activeIndex, nonce, sources]);

  return (
    <section className="ui-source-panel" aria-labelledby={headingId}>
      <header className="ui-source-panel__header">
        <div className="ui-source-panel__heading">
          <h2 id={headingId} className="ui-source-panel__title">
            Sources
            {sources.length > 0 && <span className="ui-source-panel__count"> · {sources.length}</span>}
          </h2>
          {(turnLabel || question) && (
            <p className="ui-source-panel__context">
              {turnLabel && <span className="ui-source-panel__turn">{turnLabel}</span>}
              {question && <span className="ui-source-panel__question">{question}</span>}
            </p>
          )}
        </div>
        {onClose && <IconButton label="Close sources" icon={<CloseIcon />} onClick={onClose} tooltip={{ align: "end" }} />}
      </header>

      <div ref={body} className="ui-source-panel__body">
        {insufficientEvidence && sources.length > 0 && (
          <Callout tone="info" title="Checked, not enough to answer">
            <p>These passages were retrieved, but the answer reported that they do not support it.</p>
          </Callout>
        )}
        {sources.length === 0 ? (
          <div className="ui-source-panel__empty">
            {state === "pending" ? (
              <LoadingIndicator label="Looking for sources..." />
            ) : (
              <p>
                {state === "idle"
                  ? "The sources of each answer appear here, numbered as they are cited."
                  : state === "failed"
                  ? "No sources: the request failed before any source was found."
                  : insufficientEvidence
                    ? "No source passed the evidence check for this question."
                    : "No sources for this answer."}
              </p>
            )}
          </div>
        ) : (
          <ol className="ui-source-panel__list">
            {sources.map((s, i) => (
              <li key={`${s.chunk_id}-${i}`} data-source-index={i}>
                <SourceItem
                  source={s}
                  n={i + 1}
                  id={`${idBase}-source-${i + 1}`}
                  active={activeIndex === i}
                  flashKey={activeIndex === i ? nonce : undefined}
                  cited={cited ? cited.has(i) : undefined}
                />
              </li>
            ))}
          </ol>
        )}
      </div>
      <p className="ui-visually-hidden" aria-live="polite">
        {announcement}
      </p>
    </section>
  );
}
