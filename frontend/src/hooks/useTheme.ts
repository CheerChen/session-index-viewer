import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";

// Resolve the initial theme: stored choice wins, otherwise fall back to
// the OS-level prefers-color-scheme signal. Hoisted so the initial state
// is computed once, synchronously, before the first paint.
function initialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  if (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches
  ) {
    return "dark";
  }
  return "light";
}

// Reflect the theme on <html data-theme="…"> so the CSS variable
// overrides in [data-theme="dark"] take effect. Kept in sync with the
// state via an effect; toggling updates both the attribute and storage.
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
