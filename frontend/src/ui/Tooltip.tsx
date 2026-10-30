import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { cx } from "./cx";

type Props = {
  content: string;
  children: ReactNode;
  placement?: "top" | "bottom";
  align?: "center" | "start" | "end"; // "start"/"end" keep the bubble inside the screen near an edge
  delay?: number; // ms before showing on hover; keyboard focus shows it at once
};

// A short visual label for a control that already has the same accessible name (IconButton passes
// its aria-label). The bubble is aria-hidden so screen readers do not hear the name twice; never put
// information only in a tooltip. Shown on hover and keyboard focus, hidden with Escape (WCAG 1.4.13).
export function Tooltip({ content, children, placement = "bottom", align = "center", delay = 400 }: Props) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const id = useId();

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const show = (wait: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), wait);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    setOpen(false);
  };

  return (
    <span
      className="ui-tooltip-anchor"
      onPointerEnter={(e) => e.pointerType === "mouse" && show(delay)}
      onPointerLeave={hide}
      onFocus={(e) => (e.target as HTMLElement).matches(":focus-visible") && show(0)}
      onBlur={hide}
      onPointerDown={hide}
      onKeyDown={(e) => e.key === "Escape" && open && (e.stopPropagation(), hide())}
    >
      {children}
      <span id={id} aria-hidden="true" className={cx("ui-tooltip", `ui-tooltip--${placement}`, `ui-tooltip--${align}`, open && "is-open")}>
        {content}
      </span>
    </span>
  );
}
