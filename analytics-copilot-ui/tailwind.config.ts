import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./store/**/*.{js,ts,jsx,tsx}",
    "./services/**/*.{js,ts,jsx,tsx}",
    "./utils/**/*.{js,ts,jsx,tsx}",
    "./types/**/*.{js,ts}",
    "./hooks/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        border: "hsl(214, 32%, 91%)",
        input: "hsl(214, 31%, 91%)",
        ring: "hsl(217, 91%, 60%)",
        background: "hsl(210, 20%, 98%)",
        foreground: "hsl(222, 47%, 11%)",
      },
      boxShadow: {
        card: "0 4px 16px rgba(15, 23, 42, 0.06)",
        soft: "0 1px 2px rgba(15, 23, 42, 0.04)",
        lift: "0 12px 40px rgba(15, 23, 42, 0.08)",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
