import { cx } from "./cx";

type Props = {
  label: string; // visible text, e.g. "Searching the corpus..."; the dots alone mean nothing
  size?: "sm" | "md";
  className?: string;
};

/** Three pulsing dots and a label. With reduced motion the dots stay still; the label remains. */
export function LoadingIndicator({ label, size = "md", className }: Props) {
  return (
    <span className={cx("ui-loading", `ui-loading--${size}`, className)}>
      <span className="ui-loading__dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="ui-loading__label">{label}</span>
    </span>
  );
}

/** One polite live region per page for progress and results ("Writing the answer...", "3 sources"). */
export function LiveStatus({ message }: { message: string }) {
  return (
    <p className="ui-visually-hidden" role="status" aria-live="polite">
      {message}
    </p>
  );
}
