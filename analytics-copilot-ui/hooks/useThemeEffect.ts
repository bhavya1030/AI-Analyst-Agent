"use client";

import { useEffect } from "react";
import { useUiStore } from "@/store/uiStore";

/** Applies light/dark class on <html> from theme preference + system preference. */
export function useThemeEffect() {
  const theme = useUiStore((s) => s.theme);
  const setResolvedTheme = useUiStore((s) => s.setResolvedTheme);

  useEffect(() => {
    const root = document.documentElement;
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const apply = () => {
      const resolved =
        theme === "system" ? (media.matches ? "dark" : "light") : theme;
      root.classList.toggle("dark", resolved === "dark");
      root.style.colorScheme = resolved;
      setResolvedTheme(resolved);
    };

    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme, setResolvedTheme]);
}
