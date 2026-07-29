"use client";

import type { ReactNode } from "react";
import TopNav from "@/components/layout/TopNav";

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <TopNav />
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
