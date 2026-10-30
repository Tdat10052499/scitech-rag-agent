import { useEffect, useId, useRef } from "react";
import type { ReactNode, RefObject } from "react";
import { cx } from "./cx";

type Props = {
  open: boolean;
  onClose: () => void; // Escape, a click on the backdrop, or a close button inside
  side?: "left" | "right";
  title: string; // the dialog's accessible name
  showTitle?: boolean; // false when the content already shows its own heading
  initialFocus?: RefObject<HTMLElement | null>; // default: the panel itself, so the title is read first
  children: ReactNode;
  className?: string;
};

// A modal side sheet on the native <dialog>: showModal() keeps focus inside and makes the rest of the
// page inert; Escape closes it; on close, focus returns to the element that opened it.
export function Drawer({ open, onClose, side = "right", title, showTitle = false, initialFocus, children, className }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      d.showModal();
      (initialFocus?.current ?? panel.current)?.focus();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open, initialFocus]);

  // If the drawer unmounts while open (e.g. the layout switches to inline), give focus back.
  useEffect(() => () => opener.current?.focus(), []);

  return (
    <dialog
      ref={dialog}
      className={cx("ui-drawer", `ui-drawer--${side}`, className)}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault(); // keep `open` controlled by the parent
        onClose();
      }}
      onClose={() => {
        opener.current?.focus();
        opener.current = null;
      }}
      onClick={(e) => e.target === dialog.current && onClose()}
    >
      <div ref={panel} className="ui-drawer__panel" tabIndex={-1}>
        <h2 id={titleId} className={showTitle ? "ui-drawer__title" : "ui-visually-hidden"}>
          {title}
        </h2>
        {children}
      </div>
    </dialog>
  );
}
