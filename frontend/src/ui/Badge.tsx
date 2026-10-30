import type { HTMLAttributes } from "react";
import { cx } from "./cx";

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: "neutral" | "accent" | "outline";
  mono?: boolean; // for codes such as arXiv categories ("cs.CL")
};

/** A small metadata label. Not interactive; for actions use Button. */
export function Badge({ tone = "neutral", mono = false, className, ...rest }: BadgeProps) {
  return <span className={cx("ui-badge", `ui-badge--${tone}`, mono && "ui-badge--mono", className)} {...rest} />;
}
