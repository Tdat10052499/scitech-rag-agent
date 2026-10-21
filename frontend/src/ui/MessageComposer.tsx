import { useId } from "react";
import type { FormEvent, Ref } from "react";
import { shouldSubmitOnKey } from "./composerKeys";
import { cx } from "./cx";
import { ArrowUpIcon } from "./icons";
import { IconButton } from "./IconButton";
import { LoadingIndicator } from "./LoadingIndicator";
import { Textarea } from "./Textarea";

export type ComposerState = "idle" | "waiting" | "streaming"; // waiting: sent, no event yet

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (text: string) => void; // trimmed, never empty
  state?: ComposerState;
  label?: string; // accessible name of the text box
  placeholder?: string;
  showHint?: boolean;
  textareaRef?: Ref<HTMLTextAreaElement>;
  className?: string;
};

const COMPOSER_MAX_HEIGHT = 200; // px, about 7 lines; then the text scrolls inside the box

const BUSY_LABEL: Record<Exclude<ComposerState, "idle">, string> = {
  waiting: "Searching the corpus...",
  streaming: "Writing the answer...",
};

/**
 * Question input. Enter sends, Shift+Enter adds a line, nothing is sent during IME composition.
 * The box grows up to COMPOSER_MAX_HEIGHT and then scrolls inside. While an answer is on its way
 * the user can keep typing, but sending waits (the API answers one question at a time; there is no
 * stop action because the current app has no way to cancel an answer on the server).
 */
export function MessageComposer({
  value,
  onChange,
  onSubmit,
  state = "idle",
  label = "Your question",
  placeholder = "Ask about LLM and NLP research...",
  showHint = true,
  textareaRef,
  className,
}: Props) {
  const inputId = useId();
  const hintId = useId();
  const busy = state !== "idle";
  const canSend = !busy && value.trim() !== "";

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (canSend) onSubmit(value.trim());
  };

  return (
    <form className={cx("ui-composer", busy && "is-busy", className)} onSubmit={submit}>
      <label htmlFor={inputId} className="ui-visually-hidden">
        {label}
      </label>
      <Textarea
        id={inputId}
        ref={textareaRef}
        variant="bare"
        autoResize
        maxHeight={COMPOSER_MAX_HEIGHT}
        value={value}
        placeholder={placeholder}
        aria-describedby={showHint && !busy ? hintId : undefined}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (shouldSubmitOnKey({ key: e.key, shiftKey: e.shiftKey, isComposing: e.nativeEvent.isComposing, keyCode: e.keyCode })) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="ui-composer__footer">
        <div className="ui-composer__status">
          {busy ? (
            <LoadingIndicator size="sm" label={BUSY_LABEL[state]} />
          ) : (
            showHint && (
              <span id={hintId} className="ui-composer__hint">
                Enter to send · Shift+Enter for a new line
              </span>
            )
          )}
        </div>
        <IconButton type="submit" variant="primary" label="Send question" icon={<ArrowUpIcon />} disabled={!canSend} tooltip={{ placement: "top", align: "end" }} />
      </div>
    </form>
  );
}
