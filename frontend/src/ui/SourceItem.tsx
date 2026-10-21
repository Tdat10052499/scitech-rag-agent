import { useState } from "react";
import type { Source } from "../types";
import { Badge } from "./Badge";
import { cx } from "./cx";
import { ExternalLinkIcon } from "./icons";
import { describeSource } from "./sourceMeta";

const LONG_SNIPPET = 220; // characters; longer excerpts start collapsed to three lines

type Props = {
  source: Source;
  n: number; // 1-based number, as cited in the answer
  active?: boolean; // shown from a citation click
  flashKey?: number; // change it to replay the highlight (a second click on the same [n])
  cited?: boolean; // false: retrieved but the answer does not cite it; undefined: not known yet
  id?: string; // DOM id, unique across turns
};

/** One retrieved source. Shows only the metadata that is present; the retrieval score is not shown. */
export function SourceItem({ source, n, active = false, flashKey, cited, id }: Props) {
  const d = describeSource(source);
  const [expanded, setExpanded] = useState(false);
  const long = (d.snippet?.length ?? 0) > LONG_SNIPPET;
  const meta = [d.kind, d.date, d.identifier].filter(Boolean);

  return (
    <div id={id} className={cx("ui-source", active && "is-active")} aria-current={active ? "true" : undefined}>
      {active && <span key={flashKey} className="ui-source__flash" aria-hidden="true" />}
      <span className="ui-source__number" aria-hidden="true">
        {n}
      </span>
      <div className="ui-source__body">
        <p className="ui-source__title">
          <span className="ui-visually-hidden">Source {n}: </span>
          {d.href ? (
            <a href={d.href} target="_blank" rel="noreferrer">
              {d.title}
              <ExternalLinkIcon size={13} className="ui-source__external" />
              <span className="ui-visually-hidden"> (opens in a new tab)</span>
            </a>
          ) : (
            <span className={cx(d.untitled && "is-untitled")}>{d.title}</span>
          )}
        </p>
        {meta.length > 0 && <p className="ui-source__meta">{meta.join(" · ")}</p>}
        {d.categories.length > 0 && (
          <p className="ui-source__categories">
            <span className="ui-visually-hidden">Categories: </span>
            {d.categories.map((c) => (
              <Badge key={c} mono>
                {c}
              </Badge>
            ))}
          </p>
        )}
        {d.snippet && (
          <>
            <p className={cx("ui-source__snippet", long && !expanded && "is-clamped")}>{d.snippet}</p>
            {long && (
              <button type="button" className="ui-text-button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
                {expanded ? "Show less" : "Show full excerpt"}
              </button>
            )}
          </>
        )}
        {(!d.href || cited === false) && (
          <p className="ui-source__notes">
            {!d.href && <span>No link available</span>}
            {cited === false && <span>Retrieved, not cited in this answer</span>}
          </p>
        )}
      </div>
    </div>
  );
}
