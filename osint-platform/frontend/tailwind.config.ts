import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink:      "#05070b",
        navy:     "#080d18",
        graphite: "#0d1320",
        panel:    "#0b1221cc",   // glass panels (used with backdrop-blur)
        panel2:   "#0f172a",
        line:     "#1f2a3a",
        line2:    "#283246",
        accent:   "#22d3ee",
        accent2:  "#a78bfa",
        signal:   "#34d399",
        warn:     "#fbbf24",
        danger:   "#f43f5e",
        muted:    "#64748b",
      },
      fontFamily: {
        display: ['"Space Grotesk"', "Inter", "system-ui", "sans-serif"],
        sans:    ['Inter', "system-ui", "sans-serif"],
        mono:    ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow:        "0 0 0 1px rgba(34,211,238,0.25), 0 8px 40px -12px rgba(34,211,238,0.35)",
        "glow-soft": "0 0 0 1px rgba(167,139,250,0.18), 0 8px 32px -16px rgba(167,139,250,0.35)",
        inset:       "inset 0 1px 0 rgba(255,255,255,0.04), inset 0 0 0 1px rgba(255,255,255,0.02)",
      },
      backgroundImage: {
        "grid-line": "linear-gradient(to right, rgba(34,211,238,0.06) 1px, transparent 1px), linear-gradient(to bottom, rgba(34,211,238,0.06) 1px, transparent 1px)",
        "radial-fade": "radial-gradient(60% 40% at 50% 0%, rgba(34,211,238,0.10), transparent 70%)",
      },
      keyframes: {
        scan: {
          "0%":   { transform: "translateY(-100%)", opacity: "0" },
          "10%":  { opacity: "0.6" },
          "90%":  { opacity: "0.6" },
          "100%": { transform: "translateY(120%)", opacity: "0" },
        },
        "pulse-ring": {
          "0%":   { boxShadow: "0 0 0 0 rgba(34,211,238,0.6)" },
          "70%":  { boxShadow: "0 0 0 14px rgba(34,211,238,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(34,211,238,0)" },
        },
        "blink": {
          "0%, 50%":   { opacity: "1" },
          "50.01%, 100%": { opacity: "0" },
        },
        "shimmer": {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "drift": {
          "0%":   { transform: "translate3d(0,0,0)" },
          "50%":  { transform: "translate3d(8px,-8px,0)" },
          "100%": { transform: "translate3d(0,0,0)" },
        },
      },
      animation: {
        scan:        "scan 3.2s ease-in-out infinite",
        "pulse-ring":"pulse-ring 1.6s cubic-bezier(0.4,0,0.6,1) infinite",
        blink:       "blink 1s steps(1) infinite",
        shimmer:     "shimmer 2.8s linear infinite",
        drift:       "drift 14s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
