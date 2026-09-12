# Hardcoded Colour Audit — PureGamma.ai frontend (before)

Measured against `cf8535ee`, before the round-5 design-system work.

## Totals

| Category | Count | Verdict |
| --- | --- | --- |
| Inline hex literals in `app/` + `components/` + `lib/` + `plugins/` | **87** across **6** files | Only brand assets are legitimate |
| `rgba(` / `rgb(` in the same tree | 14 | Should resolve through tokens, with the alpha ramp in the token table |
| `boxShadow` / arbitrary `shadow-[…]` | 2 | No elevation language exists |
| Inline `style={{…}}` objects | 96 | Where token discipline leaks |

## By file

| File | Hex | Assessment |
| --- | --- | --- |
| `components/global-market-terminal.tsx` | 68 | **Legitimate** — currency logos and flag colours. Keep, and keep them gathered in one named constant |
| `lib/theme.ts` | 13 | **Dead code** — `pgTokens` is imported only by `components/theme/tokens.ts`, which nothing imports. Delete both |
| `components/trading-architecture.tsx` | 3 | One is `var(--text-pg, #9ca3af)`, a fallback for an **undeclared** variable. Fix the variable, drop the fallback |
| `components/backtest-terminal.tsx` | 1 | Should be a token |
| `components/research-mode-switch.tsx` | 1 | Should be a token |
| `components/secretary-console.tsx` | 1 | Should be a token |

**Component-level target after this round: 68 (assets only).** The remaining 19
are all removable.

## Palette literals in `tailwind.config.ts`

These bypass the theme entirely and are the root cause of defect D1:

| Key | Value | Used | Action |
| --- | --- | --- | --- |
| `pg-white` | `#FFFFFF` | 45 lines | Replace with `--pg-surface-inverse` / `--pg-text-inverse`, then delete |
| `pg-black` | `#101216` | 45 lines | Same |
| `pg-black-soft` | `#15181e` | 0 | Delete |
| `pg-panel` | `#191c22` | 0 | Delete |
| `pg-panel-2` | `#212123` | 0 | Delete |
| `pg-panel-3` | `#292929` | 0 | Delete |
| `pg-white-soft` | `#F4F4F5` | 0 | Delete |
| `pg-text` | `#F5F6F8` | 0 | Delete |
| `pg-muted` | `#A2A4A6` | 0 | Delete |
| `pg-muted-2` | `#7F8287` | 0 | Delete |
| `bg-card-hover` | `#212123` | 0 | Delete — a hardcoded dark hover that would be wrong in light theme |
| `canvas` / `ink` / `line` / `positive` / `warning` / `danger` (legacy block) | literal hex | **0 each** | Delete the whole block |

## Undefined variable references

| Variable | Referenced at | Fallback |
| --- | --- | --- |
| `--bg-panel` | `globals.css` 343, 362, 376 | none → declaration void |
| `--border-pg` | `globals.css` 363, 377 | none → declaration void |
| `--text-pg` | `trading-architecture.tsx` 44 | `#9ca3af` |

None of the three is declared anywhere in the repository.

## Reference targets

- Components: **0** hex except the single named brand-asset constant.
- Token table: alpha ramps expressed as `rgba()` in **one** place per theme.
- `rgba()` in components: 0.
