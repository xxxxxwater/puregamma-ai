# UI Theme Audit — PureGamma.ai frontend

Measured against `cf8535ee` (branch `main`). Every number below came from
scanning this repository; nothing is estimated.

Companion documents: `UI_DENSITY_AUDIT.md`, `HARDCODED_COLOR_AUDIT.md`.

---

## 1. Shape of the file

| Thing | Measured |
| --- | --- |
| `apps/web/app/globals.css` | 940 lines, 211 rule blocks |
| Custom-property declarations | 146 |
| Distinct custom-property names | 74 |
| `data-theme` occurrences in CSS | 18 |
| `data-visual-style` occurrences in CSS | 70 |
| `data-surface-tier` occurrences in CSS | 11 |
| `backdrop-filter` | 29 |
| `gradient(` | 33 |

**The ratio is the headline: `data-visual-style` appears almost four times as
often as `data-theme`.** The glass skin, not the theme, is what currently
carries the most weight in the stylesheet.

---

## 2. Five token families, one of which breaks the others

Names grouped by their prefix, as declared in `globals.css`:

| Family | Count | Declared where | Notes |
| --- | --- | --- | --- |
| `--ocean-*` | 11 | `:root` only | No light variant |
| `--accent-*` | 9 | line 566 (late) | First used at line 610 |
| `--glass-*` | 8 | glass blocks | Skin-local, fine |
| `--lens-*` | 8 | glass blocks | Skin-local, fine |
| `--admin-*` | 7 | both themes | Complete |
| `--secretary-*` | 4 | both themes | Complete |
| `--panel*`, `--border*`, `--bg*` | 9 | `:root` + light | Semantic base |
| `--font*`, `--radius*`, `--section*` | 5 | `:root` | Scale tokens |
| state (`--positive` … `--info`) | 4 | both themes | No `-soft` variants |

### The structural defect

`globals.css` lines 409–458 declare glass as:

```css
:root[data-visual-style="glass"] {
  --panel: rgba(19, 26, 38, 0.90);
  --border: …;
}
```

**The skin layer rewrites the semantic tokens.** `--panel` therefore has two
different truths depending on an attribute that has nothing to do with the
theme. Any future third theme has to be correct against both, and the "one
source of truth" property that makes a design system maintainable is lost.

---

## 3. Theme engine

| Property | Current state | Consequence |
| --- | --- | --- |
| Default theme | Dark (`:root` is dark, `:root[data-theme="light"]` overrides) | Light users pay the cost of a reverse-defined system |
| Pre-paint script for theme | **absent** (`app/layout.tsx` inlines only `data-visual-style`) | Theme is applied in a `useEffect`, i.e. after hydration |
| Flash on reload | **present for every light-theme user** | First paint is dark, then it flips |
| `data-font-scale` pre-paint | **absent** | Mounted at 16px, then reflows to 14/18px |
| `prefers-color-scheme` anywhere in source | **0** | No System option |
| Theme preference values | `"dark"` / `"light"` only | Binary, no `system` |
| `color-scheme` (CSS or JS) | **0 occurrences** | Native `<select>` popups, scrollbars and `input[type=date]` follow the OS, not the app |
| `<AppearanceControls>` mount points | **3** (`nav.tsx` rail, top bar desktop, top bar mobile) | Three independent `useState`; no storage listener, no cross-tab sync |

The three mount points are the visible symptom: switching theme in the top bar
leaves the rail's icon stale until reload.

---

## 4. Confirmed defects (each verified in this repository)

### D1 — Inverted buttons lose their edge in light theme

| Metric | Value |
| --- | --- |
| Lines containing `bg-pg-white` / `text-pg-black` | **45** |
| Total occurrences | **90** |
| Files affected | **30** |

`tailwind.config.ts` hardcodes `pg-white: #FFFFFF` and `pg-black: #101216`, so
they do not follow the theme. In light theme `--panel` is also `#ffffff`:
the primary button becomes white-on-white with a near-invisible border. This is
the single largest visual-language defect in the product.

### D2 — Markdown has no styling at all

`components/puregamma.tsx` renders answers through:

```
prose prose-invert prose-headings:text-text-pg prose-p:text-text-pg-muted
prose-li:text-text-pg-muted prose-strong:text-text-pg
```

- `@tailwindcss/typography` is **not** in `package.json`, and `plugins: []`.
- Those class names therefore produce **0 CSS rules**.
- `.pg-report` is referenced in the class list and **defined nowhere**.
- `remark-gfm` is referenced **0 times** → pipe tables are not parsed.
- No `components={{}}` passed to `ReactMarkdown`, so headings inherit body
  size, lists lose their markers and indent from preflight, blockquotes and
  tables have no styling, and code blocks have no header, language label or copy
  control.

This is the highest return-on-effort fix in the whole audit: Chat is the core
product surface and its answers are currently unformatted text.

### D3 — Focus visibility only exists for one skin

`globals.css` contains exactly **one** `focus-visible` rule:

```css
[data-visual-style="glass"] :focus-visible { outline: 2px solid var(--accent); … }
```

- Scoped to glass → in the classic skin the entire product has no focus ring.
- `outline-none` appears **33 times** in components, against **2**
  `focus-visible` occurrences in source.

### D4 — Chat width contract differs by route

| Route | Wrapper | Effective content column |
| --- | --- | --- |
| `/chat` | `ChronoSlices` → `IntelligenceShell` (`.intelligence-shell{max-width:1180px}`) | narrower |
| `/chat/[conversationId]` | **none** — renders `<AgentChat>` bare | wider |

`AppShell` caps at `max-w-[1440px]`. Navigating between the two chat routes
moves the text column by roughly 100–200px depending on viewport and font scale.
`max-w-3xl` is `48rem`, which is `672 / 768 / 864px` at the three
`data-font-scale` values — the measure is not stable.

### D5 — Chat history is unreachable below 1024px

`components/agent-chat.tsx` hides the conversation sidebar with `hidden … lg:flex`
and there is **no drawer**. Below 1024px a user loses the conversation list,
"new conversation", and "delete all history". The only way back to an old
conversation is a link on `/dashboard` or typing the URL.

### D6 — Long content is silently clipped in Chat

`agent-chat.tsx` (564 lines) contains **0** `break-words` and **0**
`overflow-x-auto`. An ancestor has `overflow-hidden`. Verified live: long
transcript text that exceeds the column is **cut with no ellipsis and no
scrollbar**.

A related measurement caveat: the existing `contrast-audit` overflow assertion
(`scrollWidth <= clientWidth + 1`) is **vacuously true** because the clipping
hides the overflow it is meant to catch. Fixing D6 requires a different
assertion.

### D7 — `useHtmlDataset` never fires

`lib/chrono.ts` builds the attribute name as `"data-" + name`, and all **5**
call sites pass the camelCase `"visualStyle"`. `getAttribute` lowercases its
argument, so it looks for `data-visualstyle` while the element carries
`data-visual-style`. It returns `null` forever, and the `MutationObserver`
watches the wrong `attributeFilter`. Consequence: `lib/visual-style.ts` reads
the attribute correctly, but every `chrono/*` consumer and
`terminal/liquid-lens.tsx` always believe the skin is glass — the classic skin
still gets glass refraction edges.

### D8 — Ocean tier has no light variant

11 `--ocean-*` tokens are declared only in `:root` (dark). `lib/visual-style.ts`
assigns the Ocean tier to `/dashboard`, `/chat`, `/research` and `/secretary`,
so those four routes render a dark-biased overlay in light theme.

### D9 — Two undefined variables disable whole declarations

`globals.css` lines 343, 362, 376 reference `var(--bg-panel)` and lines 363,
377 reference `var(--border-pg)`. **Neither name is declared anywhere**, and
neither has a fallback, so the entire declaration is invalid at
computed-value time — the affected rule (a visible flowing border) simply
disappears. A fifth, `var(--text-pg, #9ca3af)` in
`components/trading-architecture.tsx`, does have a fallback.

### D10 — Contrast

Carried over from the previous round and re-measured:

| Combination | Ratio | Requirement |
| --- | --- | --- |
| light `--muted-2` on `--panel-strong` | 4.50:1 | 4.5:1 — exactly at the threshold, used at 9–11px |
| light `--negative` on `--panel-muted` | 4.52:1 | 4.5:1 — at the threshold |
| `#fff` on dark `--accent` (`.command-submit`) | 3.16:1 | **fails** AA for its 11.5px text |

`--muted-2` carries the smallest type in the product, so it is the token with
the least headroom.

---

## 5. Scale tokens

`tailwind.config.ts` declares `borderRadius` at the **top level of `theme`**,
not inside `extend`, so it replaces Tailwind's scale. Every step is one notch
larger than native:

| Utility | This project | Tailwind default |
| --- | --- | --- |
| `lg` | 0.75rem (12px) | 0.5rem (8px) |
| `xl` | 1rem (16px) | 0.75rem (12px) |
| `2xl` | 1.25rem (20px) | 1rem (16px) |
| `3xl` | 1.5rem (24px) | 1.5rem |

Usage: `rounded-lg` 333, `rounded-xl` 115, `rounded-full` 30, `rounded-2xl` 26,
`rounded-3xl` **0**. The practical effect is that `rounded-xl` — the common
surface radius — is 16px, which reads soft/consumer rather than precise.

`darkMode` is **not configured**, so Tailwind v3 defaults to `'media'`. Anyone
writing a `dark:` variant would silently bind it to the operating system rather
than the app's theme switch. Current `dark:` usage is **1 occurrence**, so the
rule is currently being followed by discipline alone, with no guard rail.

`boxShadow` extension keys (panel / card / card-hover / glow-cyan /
glow-emerald) are unreferenced; only **2** `boxShadow|shadow-[` usages exist in
all of `app/` + `components/`. There is no elevation scale in use.

---

## 6. Untouched from the brief you were given

These claims in the previous draft do **not** match this repository:

| Claim | Reality |
| --- | --- |
| "`--accent` is used before it is defined" | Defined line 566, first `var()` use line 610 — ordered correctly |
| "2380 border utility classes" | **818** |
| "`<Input>` used by only ~3 files, so ~30 files hand-roll forms" | `<Input>` 55 usages, `<Field>` 39, `<Select>` 13, all from `components/ui.tsx`. There **is** duplication, but it is 28 hand-rolled input strings across 14 files, not 30 |
| "`components/ui.tsx` Card/Badge both dead" | `Card` is dead (0 usages). `Badge` is dead **in `ui.tsx`**, but `puregamma.tsx` exports a second `Badge` used by 24 files — a duplicate primitive, not an unused one |
| "`--admin-*` / `--ocean-*` have consumers" | `--admin-*`, yes. `--ocean-*` — see D8 |
| "71 / 74 tokens are page-level colours" | 74 names span 5 families; only the base + state families are theme-wide |

Claims that **did** check out, in full: the 45-line / 90-occurrence inverted
button count, the prose-with-no-plugin defect, the single glass-scoped
`focus-visible` rule, the two chat routes with different widths, the
`useHtmlDataset` attribute bug, the five call sites, the zero `color-scheme`
declarations, the zero `prefers-color-scheme` matches, the three
`AppearanceControls` mounts, the `borderRadius`-outside-`extend` structure, the
missing `darkMode` config, `dark:` at ~0, and the undefined `--bg-panel` /
`--border-pg` references.

---

## 7. Reference: how DeepSeek structures its tokens

Measured by fetching DeepSeek's public assets and listing **custom-property
names only** (no values, no class names). 11 assets scanned, 353 distinct names.

Their layering is three-tier, and the tiers are named:

| Tier | Prefix group | Names | Purpose |
| --- | --- | --- | --- |
| Static ramps | `static-neutral`, `static-blue`, `static-red`, `static-green`, `static-amber`, `static-deepseek` | 72 | Raw scale steps. Never used directly by components |
| Semantic aliases | `alias-bg`, `alias-label`, `alias-border`, `alias-button`, `alias-state`, `alias-interactive`, `alias-markdown`, `alias-brand` | 69 | The only colours a feature component consumes |
| Component slots | `specific-sidebar`, `specific-input`, `specific-menu`, `specific-bubble`, `specific-login` | 9 | Narrow slots where generic semantics are not enough |

Plus a **scale family** — `space-1 … space-6`, `radius-sm / input / card /
panel / media / pill` — which is conventions, not design, and is the part most
worth adopting verbatim.

Two details that matter for how PureGamma should migrate:

1. **They keep two namespaces live at once** (`--ds-*` with 83 names alongside
   `--dsw-*` with 158). A compatibility alias layer during a rebuild is a
   practice they themselves use, not a shortcut.
2. **Their layering is one-directional.** Components consume `alias-*` and
   `specific-*`; nothing outside the token layer writes `static-*`, and no skin
   rewrites an alias. That one-directional property is precisely what
   `[data-visual-style="glass"]` violates in this repository.

What is **not** transferable: their colour values. Adopting them would make
PureGamma look like DeepSeek rather than like a mature investment workspace.
The structure above is the portable part.
