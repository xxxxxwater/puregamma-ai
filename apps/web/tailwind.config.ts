import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── PGResearch black / white institutional tokens ──
        "pg-black": "#030303",
        "pg-black-soft": "#080808",
        "pg-panel": "#0D0D0D",
        "pg-panel-2": "#111111",
        "pg-panel-3": "#161616",
        "pg-white": "#FFFFFF",
        "pg-white-soft": "#F4F4F5",
        "pg-text": "#EDEDED",
        "pg-muted": "#A3A3A3",
        "pg-muted-2": "#737373",

        // ── Semantic tokens required by the UI brief ──
        "bg-app": "var(--background)",
        "bg-panel": "var(--panel)",
        "bg-panel-muted": "var(--panel-muted)",
        "bg-app-elevated": "var(--panel-muted)",
        "bg-card": "var(--panel)",
        "bg-card-muted": "var(--panel-muted)",
        "bg-card-hover": "#161616",

        // ── Borders ──
        "border-pg": "var(--border)",
        "border-pg-strong": "var(--border-strong)",
        "border-subtle": "var(--border)",
        "border-default": "var(--border)",
        "border-emphasis": "var(--border-strong)",

        // ── Text ──
        "text-pg": "var(--foreground)",
        "text-pg-muted": "var(--muted)",
        "text-pg-dim": "var(--muted-2)",
        "text-primary": "var(--foreground)",
        "text-secondary": "var(--muted)",
        "text-tertiary": "var(--muted-2)",
        "text-muted": "var(--muted-2)",

        // ── Low saturation state colors only ──
        "status-positive": "var(--positive)",
        "status-negative": "var(--negative)",
        "status-warning": "var(--warning)",
        "accent-cyan": "var(--info)",
        "accent-cyan-muted": "rgba(212, 212, 216, 0.10)",
        "accent-emerald": "var(--positive)",
        "accent-emerald-muted": "rgba(217, 249, 157, 0.10)",
        "accent-amber": "var(--warning)",
        "accent-amber-muted": "rgba(253, 230, 138, 0.10)",
        "accent-red": "var(--negative)",
        "accent-red-muted": "rgba(252, 165, 165, 0.10)",

        // ── Risk / Status Semantic ──
        "risk-low": "var(--positive)",
        "risk-medium": "var(--warning)",
        "risk-high": "var(--negative)",
        "status-healthy": "var(--positive)",
        "status-failed": "var(--negative)",
        "status-inactive": "var(--muted-2)",

        // ── Keep legacy token names for backward compatibility ──
        canvas: "#f7f7f4",
        ink: "#171717",
        line: "#dfded8",
        positive: "#10805f",
        warning: "#b45309",
        danger: "#b91c1c",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "'Segoe UI'",
          "Roboto",
          "sans-serif",
        ],
        mono: ["'JetBrains Mono'", "'Fira Code'", "monospace"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
        eyebrow: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.08em", fontWeight: "600" }],
      },
      boxShadow: {
        panel: "none",
        card: "none",
        "card-hover": "0 0 0 1px rgba(255,255,255,0.18)",
        "glow-cyan": "none",
        "glow-emerald": "none",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.25rem",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      backgroundImage: {
        "grid-pattern":
          "linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)",
      },
      backgroundSize: {
        "grid": "40px 40px",
      },
    },
  },
  plugins: [],
};

export default config;
