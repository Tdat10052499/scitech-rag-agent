import { useCallback, useLayoutEffect, useRef } from "react";
import type { Ref, TextareaHTMLAttributes } from "react";
import { cx } from "./cx";

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  variant?: "field" | "bare"; // field: bordered input; bare: no frame (inside the composer)
  autoResize?: boolean; // grow with the content up to maxHeight, then scroll inside
  maxHeight?: number; // px
  ref?: Ref<HTMLTextAreaElement>;
};

export function Textarea({ variant = "field", autoResize = false, maxHeight = 200, className, ref, value, rows = 1, ...rest }: TextareaProps) {
  const inner = useRef<HTMLTextAreaElement | null>(null);
  const setRef = useCallback(
    (el: HTMLTextAreaElement | null) => {
      inner.current = el;
      if (typeof ref === "function") ref(el);
      else if (ref) ref.current = el;
    },
    [ref],
  );

  useLayoutEffect(() => {
    const el = inner.current;
    if (!el || !autoResize) return;
    const style = getComputedStyle(el);
    const borders = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    el.style.height = "auto";
    const needed = el.scrollHeight + borders;
    el.style.height = `${Math.min(needed, maxHeight)}px`;
    el.style.overflowY = needed > maxHeight ? "auto" : "hidden";
  }, [value, autoResize, maxHeight]);

  return <textarea ref={setRef} value={value} rows={rows} className={cx("ui-textarea", `ui-textarea--${variant}`, className)} {...rest} />;
}
