import { useId } from "react";
import type { ReactNode } from "react";
import { cx } from "./cx";
import { MonitorIcon, MoonIcon, SunIcon } from "./icons";
import type { ThemePreference } from "./theme";

type Props = {
  value: ThemePreference;
  onChange: (value: ThemePreference) => void;
  showLabels?: boolean; // false: icons only (names stay available to screen readers)
  className?: string;
};

const OPTIONS: Array<{ value: ThemePreference; label: string; icon: ReactNode }> = [
  { value: "system", label: "Auto", icon: <MonitorIcon size={16} /> },
  { value: "light", label: "Light", icon: <SunIcon size={16} /> },
  { value: "dark", label: "Dark", icon: <MoonIcon size={16} /> },
];

/** Segmented control built on native radio buttons (arrow keys move between options). */
export function ThemeToggle({ value, onChange, showLabels = true, className }: Props) {
  const name = useId();
  return (
    <fieldset className={cx("ui-segmented", className)}>
      <legend className="ui-visually-hidden">Color theme</legend>
      {OPTIONS.map((o) => (
        <label key={o.value} className={cx("ui-segmented__option", value === o.value && "is-checked")} title={showLabels ? undefined : o.label}>
          <input
            type="radio"
            className="ui-visually-hidden"
            name={name}
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
          />
          {o.icon}
          <span className={showLabels ? undefined : "ui-visually-hidden"}>{o.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
