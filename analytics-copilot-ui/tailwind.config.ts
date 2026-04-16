import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}", "./store/**/*.{js,ts,jsx,tsx}", "./services/**/*.{js,ts,jsx,tsx}", "./utils/**/*.{js,ts,jsx,tsx}", "./types/**/*.{js,ts}", "./hooks/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(214, 32%, 91%)",
        input: "hsl(214, 31%, 91%)",
        ring: "hsl(214, 50%, 60%)",
        background: "hsl(210, 24%, 16%)",
        foreground: "hsl(210, 16%, 93%)",
      },
      boxShadow: {
        card: "0 10px 30px rgba(15, 23, 42, 0.12)",
      },
    },
  },
  plugins: [],
};

export default config;
