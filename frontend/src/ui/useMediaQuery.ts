import { useCallback, useSyncExternalStore } from "react";

/** True while the media query matches; updates on resize, zoom or OS setting changes. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (notify: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", notify);
      return () => mql.removeEventListener("change", notify);
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => false);
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Layout breakpoints (px). CSS custom properties cannot be used in media queries, so layout.css
 * repeats these numbers; change both together.
 */
export const BREAKPOINTS = {
  sidebarInline: 1280, // below: the sidebar is a drawer
  sourcesInline: 1024, // below: the sources panel is a drawer
} as const;
