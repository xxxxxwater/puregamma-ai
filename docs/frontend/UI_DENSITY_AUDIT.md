# UI Density Audit — PureGamma.ai frontend

Measured against `cf8535ee`. Companion to `UI_THEME_AUDIT.md`.

The goal of this round is **lower density, not fewer features**. Every number
below is a measurement, and every target is a reduction with a stated reason.

---

## 1. Global counters

| Metric | Now | Target | Why |
| --- | --- | --- | --- |
| `border-*` utility classes | **818** | ≤ 450 | A border is the most expensive way to express grouping. Replace with whitespace, type hierarchy, or a single hairline. |
| `bg-bg-panel` / `card` / `app` / `panel-muted` | **349** | keep | Surfaces are fine; it is their count of *bordered* containers that reads as heavy |
| `text-text-pg*` | 967 | keep | Already fully token-driven — this is the repository's strongest habit |
| raw `<button` | **176** | ≤ 80 | 189 `<Button>` usages exist, so a button system is available; the raw ones each carry their own padding/radius/border string |
| `<Badge>` | 57 | ≤ 30 | Badges should mark an exception, not decorate the normal state |
| `outline-none` | 33 | ≤ 10 | Each one owes a visible focus replacement |
| `focus-visible` in source | **2** | ≥ 15 | See D3 |
| `style={{…}}` inline | 96 | ≤ 40 | Inline style is where token discipline leaks |
| `boxShadow` / `shadow-[` | **2** | — | There is no elevation language at all; do not invent one — adopt a 3-step scale |
| `rgba(` in components | 14 | 0 except assets | Should resolve through tokens |
| inline hex in components | **87** across 6 files | ~68 (assets only) | 68 are brand/country colours in `global-market-terminal.tsx`, which are legitimately literal |

Border classes by file (top of the distribution):

```
94  components/live-trading-console.tsx
56  components/agent-chat.tsx
43  components/api-docs-embed.tsx
43  components/puregamma.tsx
38  components/strategy-runtime-console.tsx
31  components/backtest-lab.tsx
26  components/memory-console.tsx
25  components/portfolio-console.tsx
24  app/[locale]/account/page.tsx
```

---

## 2. Card count per page

| Page | Cards | Badges | Metrics |
| --- | --- | --- | --- |
| `account` | **8** | 1 | 0 |
| `billing` | **6** | 6 | 0 |
| `admin` | 5 + 4 metrics | 0 | 4 |
| `signals` | 3 | 0 | **5** |
| `options` | 2 | 1 | 4 |
| `admin/stripe-events` | 2 | 3 | 3 |
| `admin/billing-intents` | 1 | 1 | 3 |

`account` renders 8 bordered cards and **0 bare sections**. Every group —
identity, subscription, credits, API, iMessage — is a box. A grouped list with
a hairline and 32px of air would say the same thing with one border instead of
eight.

`signals` renders 5 metric cards where a 5-row statistic strip would read
faster (label left, value right, no borders).

`billing` renders 6 cards plus 6 badges, mostly describing the current plan.

---

## 3. Homepage, first screen

Measured on `/zh` at 1440×900.

| Element | Count | Target |
| --- | --- | --- |
| Primary CTAs in hero | **3** (`开始对话` / `API 快速接入` / `查看定价`) | **2** |
| Announcement renderings of the same fact | **3** (hero banner, model card, footer rotator) | **1** |
| Bordered containers in first screen | **23** | ≤ 8 |
| — of which architecture-diagram nodes | **17** (`trading-architecture.tsx` `NodeCard`) | 0 bordered nodes |
| Brand lockup inside a card (duplicating the sidebar) | 1 | 0 |

The architecture diagram is a fixed `h-[520px]` canvas whose nodes are bordered
boxes with `text-[0.58rem]` labels. It contributes 17 of the 23 borders on the
first screen and is not readable on a phone.

`landing-footer-rotator.tsx` auto-rotates a message every 4500ms. Automatic
motion that carries no user value is noise; the copy it rotates duplicates the
model card.

---

## 4. Chat: persistent UI elements

The composer area renders **6 stacked rows** before the textarea:

| Row | Content | Verdict |
| --- | --- | --- |
| 1 | Research-mode switch + a sentence explaining it | sentence is explanatory noise; the switch belongs inside the composer |
| 2 | "Model for this turn" label + `<select>` | the label restates the control; a model chip inside the composer is enough |
| 3 | Model-availability warning | **keep** — only renders when abnormal, which is the correct behaviour |
| 4 | "Advanced research settings" collapsed card with its own border | remove the border, keep the affordance |
| 5 | attach / textarea / send | this is the composer proper |
| 6 | footer line + `Estimated cost: - Credits` | the estimate renders before a quote exists; show it only when there is one |

Target: **2 rows** (composer + optional abnormal-state line).

Other persistent elements on Chat:

| Element | Verdict |
| --- | --- |
| Sidebar header: `{remaining}/{limit} remaining · {balance} Credits` | keep, demote to tertiary |
| `ocean-shell.tsx` floating "Motion / Static" button pinned over the card's top-right | move into settings |
| 3 cross-links under the latest answer | show only once sources are opened |
| 4 starter cards in the empty state | **3** |

---

## 5. Vertical budget on Chat

Measured at 1440×900 on `/zh/chat`:

- `IntelligenceShell` header (eyebrow + display heading at
  `clamp(2.6rem,6vw,4.2rem)` + byline) occupies roughly the top fifth.
- The chat card is `h-[calc(100dvh-7rem)] min-h-[620px]`, so document height
  exceeds the viewport by the header's height.
- **Net effect, confirmed in the screenshot: the composer is below the fold.**

On a 390×844 phone the same header plus the empty-state block pushes the
composer off-screen entirely.

The composer is the primary control of this product. It must be visible without
scrolling at 1440×900 and at 390×844.

---

## 6. What is already right — do not redo

Stated explicitly so the next round does not spend budget here:

- **Zero `dark:` variants.** The discipline of themeing through variables is
  already established; the work is to make the token table trustworthy, not to
  introduce the habit.
- **967 token-driven text utilities** — colour is not hardcoded in components
  (87 hex total, 68 of them legitimate brand assets).
- **`app/` contains almost no hardcoded colour** — the discipline is strongest
  exactly where it matters most.
- **Agent stage indicator and tool chips are already small inline rows**, not
  full-panel loaders. Keep them.
- **The assistant message is already non-carded** (a left border and padding).
  Keep that; it is the right direction.
- **`admin-users-table.tsx`** already does server-side filtering and paging with
  a stale-response guard, and `admin/layout.tsx` already marks the active nav
  item with a subtle surface rather than a colour block.
- **Contrast was already measured and fixed** for four tokens last round
  (`--muted-2`, light `--positive`, light `--warning`). Three borderline cases
  remain (see `UI_THEME_AUDIT.md` §4 D10) — fix those, do not re-litigate the
  rest.
