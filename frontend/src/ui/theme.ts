import { useCallback, useEffect, useState } from "react";

// Theme preference: "system" follows the OS (prefers-color-scheme); "light" and "dark" set
// data-theme on <html>, which tokens.css turns into `color-scheme`. Stored per browser; storage may
// be unavailable (private mode), so every access is guarded and the default is "system".

export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "scitech-theme";

export function readThemePreference(): ThemePreference {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyThemePreference(pref: ThemePreference, root: HTMLElement = document.documentElement) {
  if (pref === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", pref);
}

/** `initial` overrides the stored value for this page load (the showcase passes ?theme= to its frame). */
export function useThemePreference(initial?: ThemePreference): [ThemePreference, (pref: ThemePreference) => void] {
  const [pref, setPref] = useState<ThemePreference>(() => initial ?? readThemePreference());
  useEffect(() => applyThemePreference(pref), [pref]);
  const update = useCallback((next: ThemePreference) => {
    setPref(next);
    try {
      if (next === "system") localStorage.removeItem(THEME_STORAGE_KEY);
      else localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // not persisted; the choice still applies to this page
    }
  }, []);
  return [pref, update];
}
