import type { ReactNode } from "react";
import { cx } from "./cx";

type Props = {
  children: ReactNode;
  label?: string;
  className?: string;
};

/** Centered column of at most --layout-reading (760px) for the conversation; long text stays readable. */
export function ReadingColumn({ children, label = "Conversation", className }: Props) {
  return (
    <section className={cx("ui-reading", className)} aria-label={label}>
      {children}
    </section>
  );
}
