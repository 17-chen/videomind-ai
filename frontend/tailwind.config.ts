import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        accent: "hsl(var(--accent))",
        "accent-foreground": "hsl(var(--accent-foreground))",
        violet: "hsl(var(--violet))",
        destructive: "hsl(var(--destructive))"
      },
      boxShadow: {
        panel: "0 18px 50px rgba(17, 17, 17, 0.07), 0 1px 0 rgba(17, 17, 17, 0.03)",
        float: "0 28px 80px rgba(17, 17, 17, 0.12)"
      }
    }
  },
  plugins: [require("tailwindcss-animate")]
};

export default config;
