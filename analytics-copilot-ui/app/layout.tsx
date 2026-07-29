import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";
import AppProviders from "@/components/providers/AppProviders";
import AppShell from "@/components/layout/AppShell";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Analytics Platform · AI Analyst",
  description:
    "Enterprise AI analytics: charts, forecasts, EDA, session memory, and open-data discovery.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className={`${inter.className} antialiased`}>
        <AppProviders>
          <AppShell>{children}</AppShell>
        </AppProviders>
      </body>
    </html>
  );
}
