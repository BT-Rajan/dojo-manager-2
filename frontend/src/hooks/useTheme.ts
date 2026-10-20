import { useSyncExternalStore } from "react";

// Light/dark theme. With no saved choice the OS preference applies; toggling saves an explicit
// choice. index.html applies the same rule before first paint so there is no flash.
const KEY = "theme";
type Theme = "light" | "dark";
const listeners = new Set<() => void>();

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function current(): Theme {
  return stored() ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function toggleTheme() {
  const next: Theme = current() === "dark" ? "light" : "dark";
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* storage unavailable: applies for this page view only */
  }
  apply(next);
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const theme = useSyncExternalStore(subscribe, () => (document.documentElement.classList.contains("dark") ? "dark" : "light"), () => "light" as Theme);
  return { theme, toggle: toggleTheme };
}
