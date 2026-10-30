import AnswerMarkdown from "../AnswerMarkdown";
import type { AssistantMessage as AssistantTurn } from "../types";
import { AnswerRating } from "./AnswerRating";
import type { AnswerRatingValue } from "./AnswerRating";
import { Button } from "./Button";
import { CitationMarker } from "./CitationMarker";
import { resolveCitation } from "./citations";
import { cx } from "./cx";
import { ErrorState } from "./ErrorState";
import { FollowUpSuggestions } from "./FollowUpSuggestions";
import { BookIcon } from "./icons";
import { InsufficientEvidenceState } from "./InsufficientEvidenceState";
import { LoadingIndicator } from "./LoadingIndicator";
import { describeSource } from "./sourceMeta";

type Props = {
  turn: AssistantTurn; // as built from the /chat events (src/types.ts)
  number?: number; // shown as "Answer 2"
  activeIndex?: number | null; // 0-based index of this answer's source shown in the panel
  sourcesShown?: boolean; // the panel currently shows this answer's sources
  onCite?: (index: number, trigger: HTMLElement) => void;
  onShowSources?: (trigger: HTMLElement) => void;
  onRetry?: () => void;
  onFollowup?: (question: string) => void; // pass only on the latest answer
  followupDisabled?: boolean; // another question is being answered
  rating?: AnswerRatingValue | null; // thumb chosen so far
  onRate?: (rating: AnswerRatingValue) => void; // pass only when the answer can be rated (it has a message id)
};

/**
 * One answer. Not a bubble: text sits on the page in the reading column. The answer text goes
 * through the existing safe renderer (src/markdown.ts, React elements only, never innerHTML).
 */
export function AssistantMessage({ turn, number, activeIndex = null, sourcesShown = false, onCite, onShowSources, onRetry, onFollowup, followupDisabled = false, rating = null, onRate }: Props) {
  const label = number === undefined ? "Answer" : `Answer ${number}`;
  const streaming = turn.status === "searching" || turn.status === "answering";
  const count = turn.sources.length;

  return (
    <article className={cx("ui-answer-turn", turn.status === "error" && "is-error")} aria-label={label} aria-busy={streaming}>
      <div className="ui-answer-turn__header">
        <span className="ui-label">{label}</span>
        {count > 0 && onShowSources && (
          <Button
            variant="ghost"
            size="sm"
            icon={<BookIcon size={15} />}
            className={cx(sourcesShown && "is-selected")}
            aria-pressed={sourcesShown}
            onClick={(e) => onShowSources(e.currentTarget)}
          >
            {count === 1 ? "1 source" : `${count} sources`}
          </Button>
        )}
      </div>

      {turn.insufficientEvidence && <InsufficientEvidenceState />}

      {turn.text !== "" && (
        <div className="ui-prose">
          <AnswerMarkdown
            text={turn.text}
            renderCite={(n) => {
              const r = resolveCitation(turn.sources, n);
              return r.kind === "source" ? (
                <CitationMarker n={n} sourceTitle={describeSource(r.source).title} active={activeIndex === r.index} onActivate={(el) => onCite?.(r.index, el)} />
              ) : (
                <CitationMarker n={n} />
              );
            }}
          />
        </div>
      )}

      {turn.status === "searching" && <LoadingIndicator label="Searching the corpus..." />}
      {turn.status === "answering" && <LoadingIndicator size="sm" label="Writing the answer..." />}
      {turn.status === "error" && turn.error && <ErrorState error={turn.error} partial={turn.text !== ""} onRetry={onRetry} />}

      {onRate && turn.status === "done" && <AnswerRating value={rating} onRate={onRate} />}

      {onFollowup && turn.status === "done" && <FollowUpSuggestions questions={turn.followups} onSelect={onFollowup} disabled={followupDisabled} />}
    </article>
  );
}
