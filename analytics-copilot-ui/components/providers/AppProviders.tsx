"use client";

import type { ReactNode } from "react";
import { useThemeEffect } from "@/hooks/useThemeEffect";

export default function AppProviders({ children }: { children: ReactNode }) {
  useThemeEffect();
  return <>{children}</>;
}
