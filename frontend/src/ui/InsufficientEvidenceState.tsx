import type { ReactNode } from "react";
import { Callout } from "./Callout";

type Props = {
  title?: string;
  children?: ReactNode; // explanation; defaults to DEFAULT_EXPLANATION
  suggestions?: string[]; // ways to rephrase; pass [] to hide
};

// Copy approved with the baseline. It states what the system does (answers only from the indexed
// corpus) and what the corpus covers (ADR 0003: arXiv cs.CL; Wikipedia was cut from v1.0); it makes
// no claim about this question. Keep the corpus sentence true if the corpus changes.
export const DEFAULT_EXPLANATION =
  "The search did not find passages that pass the evidence check, so the assistant does not answer from its own knowledge.";

export const DEFAULT_SUGGESTIONS = [
  "Name a specific method, model, dataset or task.",
  "Use the English terms that papers use.",
  "The corpus covers LLM and NLP research papers on arXiv (cs.CL): titles and abstracts.",
];

/** An answer state, not a failure: the request worked, the corpus had too little to answer from. */
export function InsufficientEvidenceState({ title = "Not enough evidence in the corpus", children, suggestions = DEFAULT_SUGGESTIONS }: Props) {
  return (
    <Callout tone="warning" title={title}>
      <p>{children ?? DEFAULT_EXPLANATION}</p>
      {suggestions.length > 0 && (
        <ul className="ui-callout__list">
          {suggestions.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      )}
    </Callout>
  );
}
