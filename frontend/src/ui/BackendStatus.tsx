import { cx } from "./cx";

type Props = {
  state: "checking" | "ok" | "down";
  label: string; // e.g. "Backend: ok"; on narrow screens only the dot is shown, the label stays as its name
};

/** Small indicator of the backend (GET /health). Colour is never the only signal: the label says it too. */
export function BackendStatus({ state, label }: Props) {
  return (
    <span className={cx("ui-status", `ui-status--${state}`)} role="status" aria-label={label} title={label}>
      <span className="ui-status__dot" aria-hidden="true" />
      <span className="ui-status__text" aria-hidden="true">
        {label}
      </span>
    </span>
  );
}
