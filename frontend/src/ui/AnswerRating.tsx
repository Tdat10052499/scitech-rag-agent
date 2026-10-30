import { cx } from "./cx";
import { IconButton } from "./IconButton";

export type AnswerRatingValue = "up" | "down";

type Props = {
  value?: AnswerRatingValue | null; // the choice made so far
  onRate: (rating: AnswerRatingValue) => void;
  className?: string;
};

// Thumbs are drawn here (24px grid, stroke = currentColor, as the icons in icons.tsx).
function Thumb({ down }: { down?: boolean }) {
  return (
    <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" style={down ? { transform: "scaleY(-1)" } : undefined}>
      <path d="M7 11v9H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h3Zm0 0 4-8a2 2 0 0 1 2 2v4h5.2a2 2 0 0 1 2 2.3l-1.1 6A2 2 0 0 1 17.1 20H7" />
    </svg>
  );
}

/** Two thumbs under a finished answer. The choice is shown as pressed; it can be changed later. */
export function AnswerRating({ value = null, onRate, className }: Props) {
  return (
    <div className={cx("ui-rating", className)} role="group" aria-label="Rate this answer">
      <span className="ui-label">Was this answer useful?</span>
      <IconButton label="Useful answer" icon={<Thumb />} size="sm" aria-pressed={value === "up"} className={cx(value === "up" && "is-selected")} onClick={() => onRate("up")} />
      <IconButton label="Not useful" icon={<Thumb down />} size="sm" aria-pressed={value === "down"} className={cx(value === "down" && "is-selected")} onClick={() => onRate("down")} />
    </div>
  );
}
