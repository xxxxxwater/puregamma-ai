import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── PGResearch grey tokens (DeepSeek console bluish scale) ──
        "pg-black": "#101216",
        "pg-black-soft": "#15181e",
        "pg-panel": "#191c22",
        "pg-panel-2": "#212123",
        "pg-panel-3": "#292929",
        "pg-white": "#FFFFFF",
        "pg-white-soft": "#F4F4F5",
        "pg-text": "#F5F6F8",
        "pg-muted": "#A2A4A6",
        "pg-muted-2": "#7F8287",

        // ── Semantic tokens required by the UI brief ──
        "bg-app": "var(--background)",
        "bg-panel": "var(--panel)",
        "bg-panel-muted": "var(--panel-muted)",
        "bg-app-elevated": "var(--panel-muted)",
        "bg-card": "var(--panel)",
        "bg-card-muted": "var(--panel-muted)",
        "bg-card-hover": "#212123",

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

        // ── Ocean visual system (Agent / Research / Today only) ──
        "ocean-blue": "#2E7DFF",
        "ocean-cyan": "#42D9FF",
        "ocean-violet": "#8B7CFF",
        "ocean-deep": "#070B12",
        "ocean-deep-panel": "#0D1420",
        "ocean-line": "rgba(66, 217, 255, 0.14)",
        "ocean-blue-muted": "rgba(46, 125, 255, 0.10)",
        "ocean-cyan-muted": "rgba(66, 217, 255, 0.08)",
        "ocean-violet-muted": "rgba(139, 124, 255, 0.08)",
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
        "card-hover": "0 0 0 1px rgba(255,255,255,0.12)",
        "glow-cyan": "none",
        "glow-emerald": "none",
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
    borderRadius: {
      none: "0px",
      sm: "0.375rem",
      DEFAULT: "0.5rem",
      md: "0.625rem",
      lg: "0.75rem",
      xl: "1rem",
      "2xl": "1.25rem",
      "3xl": "1.5rem",
      full: "9999px",
    },
  },
  plugins: [],
};

export default config;
