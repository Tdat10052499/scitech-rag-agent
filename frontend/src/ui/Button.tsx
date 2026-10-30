import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";
import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "ghost";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant; // primary: one main action per area; secondary: bordered; ghost: quiet, in toolbars and rows
  size?: "sm" | "md";
  icon?: ReactNode; // shown before the label
  ref?: Ref<HTMLButtonElement>;
};

export function Button({ variant = "secondary", size = "md", icon, className, children, type = "button", ...rest }: ButtonProps) {
  return (
    <button type={type} className={cx("ui-button", `ui-button--${variant}`, `ui-button--${size}`, className)} {...rest}>
      {icon}
      {children !== undefined && <span className="ui-button__label">{children}</span>}
    </button>
  );
}
