// Keyboard rule of the message composer: Enter sends, Shift+Enter inserts a line break, and nothing is
// sent while an input method (IME) is composing, for example a Vietnamese or Japanese keyboard where
// Enter confirms the composed text. Safari reports the Enter that ends a composition with
// isComposing = false but keyCode 229, so both are checked.

export type ComposerKey = {
  key: string;
  shiftKey: boolean;
  isComposing: boolean;
  keyCode?: number;
};

export function shouldSubmitOnKey(e: ComposerKey): boolean {
  if (e.key !== "Enter" || e.shiftKey) return false;
  if (e.isComposing || e.keyCode === 229) return false;
  return true;
}
