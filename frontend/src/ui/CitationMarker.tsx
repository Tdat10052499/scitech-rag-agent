import { cx } from "./cx";

type Props = {
  n: number; // the number as written in the answer
  sourceTitle?: string; // title of source n of the same answer; absent = the answer has no source n
  active?: boolean; // this source is the one shown in the sources panel
  onActivate?: (trigger: HTMLButtonElement) => void;
};

/**
 * "[n]" in an answer. With a matching source it is a button that shows that source; without one it is
 * a dashed, non-interactive marker that says so (it is never pointed at another source).
 */
export function CitationMarker({ n, sourceTitle, active = false, onActivate }: Props) {
  if (sourceTitle === undefined) {
    return (
      <span className="ui-citation is-missing" title={`Source ${n} is not in the list for this answer`}>
        <span aria-hidden="true">{n}</span>
        <span className="ui-visually-hidden">[{n}] (source {n} is not in the list for this answer)</span>
      </span>
    );
  }
  return (
    <button
      type="button"
      className={cx("ui-citation", active && "is-active")}
      aria-label={`Source ${n}: ${sourceTitle}`}
      aria-current={active ? "true" : undefined}
      onClick={(e) => onActivate?.(e.currentTarget)}
    >
      {n}
    </button>
  );
}
