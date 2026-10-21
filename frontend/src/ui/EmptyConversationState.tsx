import { useId } from "react";
import { FollowUpSuggestions } from "./FollowUpSuggestions";

type Props = {
  title?: string;
  description?: string;
  examples?: string[];
  onSelectExample?: (question: string) => void;
};

/** First screen of a conversation: the only place the display serif is used at size. */
export function EmptyConversationState({
  title = "What would you like to know about language-model research?",
  description = "Answers come only from indexed research papers, with a numbered source for each claim.",
  examples = [],
  onSelectExample,
}: Props) {
  const titleId = useId();
  return (
    <section className="ui-empty" aria-labelledby={titleId}>
      <h2 id={titleId} className="ui-display">
        {title}
      </h2>
      <p className="ui-empty__description">{description}</p>
      {examples.length > 0 && onSelectExample && (
        <FollowUpSuggestions title="Try one of these" questions={examples} onSelect={onSelectExample} />
      )}
    </section>
  );
}
