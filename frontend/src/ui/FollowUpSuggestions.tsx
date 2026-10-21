import { useId } from "react";
import { cx } from "./cx";
import { ArrowRightIcon } from "./icons";

export const MAX_SUGGESTIONS = 4; // the API sends at most 4 follow-ups (contract 0.2.1)

type Props = {
  questions: string[];
  onSelect: (question: string) => void; // the page decides: fill the composer or send at once
  title?: string;
  className?: string;
};

/** Suggested questions as a list of full-width rows (long questions wrap instead of being cut). */
export function FollowUpSuggestions({ questions, onSelect, title = "Follow-up questions", className }: Props) {
  const headingId = useId();
  const shown = questions.slice(0, MAX_SUGGESTIONS);
  if (shown.length === 0) return null;
  return (
    <section className={cx("ui-suggestions", className)} aria-labelledby={headingId}>
      <h3 id={headingId} className="ui-label">
        {title}
      </h3>
      <ul className="ui-suggestions__list">
        {shown.map((q) => (
          <li key={q}>
            <button type="button" className="ui-suggestions__item" onClick={() => onSelect(q)}>
              <span>{q}</span>
              <ArrowRightIcon size={16} className="ui-suggestions__icon" />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
