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

        // ── Semantic tokens ──
        // Phase 1: every value below now points at the `--pg-*` semantic
        // namespace instead of the legacy raw tokens. The class names are
        // deliberately unchanged (`bg-bg-panel`, `text-text-pg`, …), so the
        // ~2000 existing utility usages migrated without a single edit, and
        // because each alias resolves to the identical value today this is a
        // zero-visual-difference change. New work should consume `--pg-*`
        // directly rather than adding another raw-token mapping here.
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