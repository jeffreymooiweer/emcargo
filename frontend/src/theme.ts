const STORAGE_KEY = "emcargo-theme";

export type Theme = "light" | "dark";

export function getStoredTheme(): Theme | null {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === "dark" || value === "light" ? value : null;
}

export function resolveTheme(): Theme {
  const stored = getStoredTheme();
  if (stored) return stored;
  return "dark";
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem(STORAGE_KEY, theme);
}

export function initTheme() {
  applyTheme(resolveTheme());
}

export function toggleTheme(): Theme {
  const next: Theme = document.documentElement.classList.contains("dark") ? "light" : "dark";
  applyTheme(next);
  return next;
}

export function applySystemTheme(): Theme {
  localStorage.removeItem(STORAGE_KEY);
  const theme: Theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.classList.toggle("dark", theme === "dark");
  return theme;
}
