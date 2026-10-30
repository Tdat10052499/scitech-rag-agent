type Props = { text: string; id?: string };

/** The user's question: a quiet block aligned right; line breaks typed with Shift+Enter are kept. */
export function UserMessage({ text, id }: Props) {
  return (
    <article id={id} className="ui-user-turn" aria-label="Your question">
      <p className="ui-user-turn__text">{text}</p>
    </article>
  );
}
