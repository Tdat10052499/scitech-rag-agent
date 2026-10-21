import type { ReactNode } from "react";
import { cx } from "./cx";
import { AlertIcon, InfoIcon, SearchMinusIcon } from "./icons";

export type CalloutTone = "info" | "warning" | "error";

type Props = {
  tone: CalloutTone;
  title: string; // always present: the state is told in words, not only by color
  icon?: ReactNode; // defaults to the tone's icon
  children?: ReactNode;
  actions?: ReactNode;
  className?: string;
};

const DEFAULT_ICONS: Record<CalloutTone, ReactNode> = {
  info: <InfoIcon />,
  warning: <SearchMinusIcon />,
  error: <AlertIcon />,
};

/**
 * A bordered note inside the reading flow. Not a live region: the page announces state changes once
 * through LiveStatus, so a callout appearing during streaming is not read twice.
 */
export function Callout({ tone, title, icon, children, actions, className }: Props) {
  return (
    <div className={cx("ui-callout", `ui-callout--${tone}`, className)}>
      <span className="ui-callout__icon">{icon ?? DEFAULT_ICONS[tone]}</span>
      <div className="ui-callout__body">
        <p className="ui-callout__title">{title}</p>
        {children && <div className="ui-callout__content">{children}</div>}
        {actions && <div className="ui-callout__actions">{actions}</div>}
      </div>
    </div>
  );
}
