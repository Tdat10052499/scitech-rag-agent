import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";
import { cx } from "./cx";
import { Tooltip } from "./Tooltip";

export type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "aria-label"> & {
  label: string; // accessible name, also shown as the tooltip
  icon: ReactNode;
  variant?: "ghost" | "secondary" | "primary";
  size?: "sm" | "md";
  tooltip?: false | { placement?: "top" | "bottom"; align?: "center" | "start" | "end" };
  ref?: Ref<HTMLButtonElement>;
};

export function IconButton({ label, icon, variant = "ghost", size = "md", tooltip = {}, className, type = "button", ...rest }: IconButtonProps) {
  const button = (
    <button
      type={type}
      aria-label={label}
      className={cx("ui-icon-button", `ui-icon-button--${variant}`, `ui-icon-button--${size}`, className)}
      {...rest}
    >
      {icon}
    </button>
  );
  return tooltip === false ? button : <Tooltip content={label} {...tooltip}>{button}</Tooltip>;
}
