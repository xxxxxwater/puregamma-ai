import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Shared PureGamma black / white identity ──
        "pg-black": "#151515",
        "pg-black-soft": "#252525",
        "pg-panel": "var(--panel)",
        "pg-panel-2": "var(--panel-muted)",
        "pg-panel-3": "var(--panel-strong)",
        "pg-white": "#FFFFFF",
        "pg-white-soft": "#F5F5F5",
        "pg-text": "var(--foreground)",
        "pg-muted": "var(--muted)",
        "pg-muted-2": "var(--muted-2)",

        // ── Semantic tokens ──
        // Existing utility classes continue to use the shared theme tokens.
        "bg-app": "var(--pg-bg-page)",
        "bg-panel": "var(--pg-surface-1)",
        "bg-panel-muted": "var(--pg-surface-2)",
        "bg-app-elevated": "var(--pg-surface-2)",
        "bg-card": "var(--pg-surface-1)",
        "bg-card-muted": "var(--pg-surface-2)",
        "bg-card-hover": "var(--pg-surface-hover)",

        // ── Borders ──
        "border-pg": "var(--pg-border-subtle)",
        "border-pg-strong": "var(--pg-border-default)",
        "border-subtle": "var(--pg-border-subtle)",
        "border-default": "var(--pg-border-default)",
        "border-emphasis": "var(--pg-border-strong)",

        // ── Text ──
        "text-pg": "var(--pg-text-primary)",
        "text-pg-muted": "var(--pg-text-secondary)",
        "text-pg-dim": "var(--pg-text-tertiary)",
        "text-primary": "var(--pg-text-primary)",
        "text-secondary": "var(--pg-text-secondary)",
        "text-tertiary": "var(--pg-text-tertiary)",
        "text-muted": "var(--pg-text-tertiary)",
        "muted-2": "var(--pg-text-tertiary)",
        "foreground": "var(--pg-text-primary)",
        "accent": "var(--pg-accent)",
        "accent-soft": "var(--pg-accent-soft)",
        "accent-ring": "var(--pg-focus-ring)",
        "border": "var(--pg-border-subtle)",

        // ── Low saturation state colors only ──
        "status-positive": "var(--pg-positive)",
        "status-negative": "var(--pg-danger)",
        "status-warning": "var(--pg-warning)",
        "accent-cyan": "var(--pg-info)",
        "accent-cyan-muted": "var(--pg-info-soft)",
        "accent-emerald": "var(--pg-positive)",
        "accent-emerald-muted": "var(--pg-positive-soft)",
        "accent-amber": "var(--pg-warning)",
        "accent-amber-muted": "var(--pg-warning-soft)",
        "accent-red": "var(--pg-danger)",
        "accent-red-muted": "var(--pg-danger-soft)",

        // ── Risk / Status Semantic ──
        "risk-low": "var(--pg-positive)",
        "risk-medium": "var(--pg-warning)",
        "risk-high": "var(--pg-danger)",
        "status-healthy": "var(--pg-positive)",
        "status-failed": "var(--pg-danger)",
        "status-inactive": "var(--pg-text-tertiary)",

        // ── Keep legacy token names for backward compatibility ──
        canvas: "var(--background)",
        ink: "var(--foreground)",
        line: "var(--border)",
        positive: "var(--positive)",
        warning: "var(--warning)",
        danger: "var(--negative)",

        // ── Legacy Ocean names now resolve to neutral, theme-aware values ──
        "ocean-blue": "var(--ocean-blue)",
        "ocean-cyan": "var(--ocean-cyan)",
        "ocean-violet": "var(--ocean-violet)",
        "ocean-deep": "var(--ocean-deep)",
        "ocean-deep-panel": "var(--ocean-deep-panel)",
        "ocean-line": "var(--ocean-line)",
        "ocean-blue-muted": "var(--ocean-layer-a)",
        "ocean-cyan-muted": "var(--ocean-layer-b)",
        "ocean-violet-muted": "var(--ocean-layer-c)",
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
        "card-hover": "0 0 0 1px var(--border-strong)",
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
          "linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)",
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
