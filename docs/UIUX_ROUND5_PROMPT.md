> ## ⚠️ 本文档已归档，请勿作为执行依据
>
> 当前的执行主稿是 **[`docs/frontend/ROUND5_PROMPT.md`](frontend/ROUND5_PROMPT.md)**，
> 其事实依据是 `docs/frontend/` 下的三份实测审计：
> `UI_THEME_AUDIT.md`、`UI_DENSITY_AUDIT.md`、`HARDCODED_COLOR_AUDIT.md`。
>
> 本文（`docs/UIUX_ROUND5_PROMPT.md`）保留为历史正文，**不要与主稿拼接执行**。
> 它有几处计数与结论经实测后已被主稿纠正，例如：
>
> | 本文说法 | 实测结果 |
> | --- | --- |
> | border 工具类 2380 处 | **818** 处 |
> | 表单原语几乎无人使用，约 30 个文件手写 | `<Input>` 55 次、`<Field>` 39 次、`<Select>` 13 次**都来自 `components/ui.tsx`**；真实重复是 28 处手写输入框 / 14 个文件 |
> | `--accent` 在使用之后才定义 | **顺序正确**：定义 566 行、首次使用 610 行 |
> | `--ocean-*` 有组件在消费，保留即可 | 11 个 `--ocean-*` **只在 `:root` 声明、没有 light 变体**，而 4 个 Ocean 路由在浅色主题下渲染偏暗叠层 |
> | `components/ui.tsx` 的 `Card`/`Badge` 都是死代码 | `Card` 死代码（0 引用）；`Badge` 在 `ui.tsx` 里死代码，但 `puregamma.tsx` 另有一套被 24 个文件使用 —— 是**重复原语**而非未使用 |
>
> 其余判断（反色按钮 45 行 / 90 处、Markdown 无样式、focus 仅 glass 门控、
> 两条 chat 路由宽度不一致、`useHtmlDataset` 属性名 bug 及 5 个调用点、
> `color-scheme` 0 处、`prefers-color-scheme` 0 处、3 处 `AppearanceControls`、
> `borderRadius` 在 `extend` 之外、`darkMode` 未配置、未定义的
> `--bg-panel` / `--border-pg`）**经核实成立**，已在主稿中保留。

---

# PureGamma.ai 第五轮 UI / UX 升级提示词
## 目标：重建 Light / Dark 双主题设计系统，让产品达到 DeepSeek Web 产品级完成度

> 本提示词已针对 `C:\Users\Administrator\Desktop\puregamma.ai` 的**真实代码**校准。
> 文中所有文件路径、行号、数值都是在本仓库实测得到的，不是示例。
> 直接整份交给主开发执行。

---

## 0. 你现在的真实起点（先读完再动手）

你是 PureGamma.ai 的 Principal Product Designer + Staff Frontend Engineer。

这一轮**不加功能，不加重构业务**。只做一件事：

> 重建视觉系统与信息密度，让 Light / Dark 成为同一套设计系统的两个完整表达，
> 并把 Chat 工作区做成真正的 AI Workspace。

### 0.1 仓库事实（实测）

| 项目 | 现状 |
|---|---|
| 前端 | Next.js 14.2.35 App Router，`apps/web`，React 18.3.1 |
| 样式 | Tailwind CSS 3.4.17，**唯一** CSS 文件 `apps/web/app/globals.css`（939 行） |
| 当前 HEAD | `cf8535ee`（分支 `main`） |
| tsc | **通过**（`npx tsc --noEmit` exit 0，本轮实测） |
| 主题默认 | **Dark 是默认主题**（`:root` = 深色，`:root[data-theme="light"]` = 覆盖） |
| 主题存储 | `localStorage.pg_theme`，值仅 `"dark"` / `"light"` |
| 系统主题 | **完全没有** `prefers-color-scheme`，全仓库 0 处 |
| 防闪 | **没有主题的 pre-paint 脚本**；`app/layout.tsx:39` 的 `beforeInteractive` 脚本只处理 `data-visual-style`。主题在 `appearance-controls.tsx:23-33` 的 `useEffect` 里才写入 → **刷新时 light 用户必然闪一下深色** |
| 视觉风格开关 | 额外存在 `data-visual-style="glass" \| "classic"`，**glass 是默认**。`globals.css` 里 `data-visual-style` 出现 **70 次**，`data-theme` 只有 18 次 |
| 玻璃/模糊 | `backdrop-filter` **29 处**；`gradient(` **33 处** |
| 圆角 | `--radius-panel: 18px`；`.shell-rail` 20px；`rounded-2xl`(20px)/`rounded-3xl`(24px)/`rounded-full` 合计 **171 次**；`999px` 药丸 **9 处**；`rounded-xl` = 1rem = 16px 且用得最多 |
| 硬编码色 | components 内 hex **82 行 / ~87 处** —— 其中 **64 行在 `global-market-terminal.tsx` 的品牌 logo / 法币旗帜色**（合理资产色）。`app/` 目录 hex **0 处**，做得很好，**不要重做这一项** |
| 颜色工具类 | `bg-bg-panel` / `bg-bg-card` / `-muted` 共 **324 次** |
| border 工具类 | **2380 次** vs surface 324 次 → **边框比面多 7 倍**，这是"卡片框框框"的根因 |
| Badge 引用 | **140 次** |
| `dark:` 变体 | **0 次**（纪律极好，保持） |
| text token 引用 | `text-text-pg*` 系列 **791 行**，全站确实走 CSS 变量 |
| 原始 `<button>` | **140 行** vs `<Button>` 组件仅 **13 个调用点 / 4 个文件** → 按钮样式重复是最大的一致性缺口 |
| Tailwind radius | `borderRadius` 声明在 `extend` **之外**（`tailwind.config.ts:137-147`），**整体替换**了默认刻度，每档都比原生大一档 |
| Tailwind `darkMode` | **未配置** → Tailwind v3 默认 `darkMode: 'media'`，将来任何人写 `dark:` 都会绑到操作系统而非 App 主题开关（**陷阱，必须显式设为 `["selector", '[data-theme="dark"]']`**） |
| `<html>` 首帧 | **没有 `data-theme`**，所以永远先画 `:root` 的深色块 → **light 用户每次刷新都闪深色**；`pg_font_scale` 同理（挂载后 16px→14/18px 重排） |
| `color-scheme` | 全仓库**未声明** → 原生 `<select>` 弹层、滚动条、date picker 跟随操作系统，不跟随 App 主题 |
| 已确认 CSS bug | `globals.css:343,362,376` 引用 `--bg-panel`、`:363,377` 引用 `--border-pg` —— **这两个变量全仓库从未定义**，无 fallback → 整条声明失效，`.ocean-flowing-border` 在 reduced-motion 与移动端分支下背景（含可见的流动边框）**直接消失** |

### 0.2 当前 CSS 里真实存在的五套互相打架的 token 体系

`globals.css` 里声明了 **146 行 / 74 个不同的自定义属性、56 个选择器块**，但它们不是一套系统：

| # | 体系 | 位置 | 例子 |
|---|---|---|---|
| 1 | 基础语义 | `:root` L33-76 / light L78-108 | `--background` `--foreground` `--panel` `--panel-muted` `--panel-strong` `--border` `--border-strong` `--muted` `--muted-2` `--positive/negative/warning/info` |
| 2 | Admin 专用蓝 | 同上 | `--admin-accent` `--admin-accent-soft` `--admin-accent-ink` `--admin-accent-fill` `--admin-accent-fill-soft` `--admin-accent-fill-faint` `--admin-shadow` |
| 3 | Ocean | L269-281 | `--ocean-blue/cyan/violet/deep/deep-panel/line/layer-a/b/c/ripple/glow`（**无 light 变体**） |
| 4 | Glass | L397-458 | `--glass-blur/saturate/edge/chrome-bg/ambient-a/b/c` + 在 `[data-visual-style="glass"]` 下**重写 `--panel`/`--panel-muted`/`--panel-strong`/`--border`**（把语义 token 变成 rgba） |
| 5 | Liquid / Lens + accent | L560-603 | `--font-display` `--accent` `--accent-strong` `--accent-soft` `--accent-ring` `--accent-violet` `--brand-gold` `--lens-*` `--radius-panel` `--section-gap` |

**关键结论：`--accent` 直到第 566 行才被定义，却已经被 Tailwind（`tailwind.config.ts:46-48`）映射并在全站使用。**
而 `tailwind.config.ts:73-78` 还藏着完全不跟随主题的 legacy 色（`canvas:#f7f7f4` `ink:#171717` `line:#dfded8`，全站零引用），`L27` 的 `bg-card-hover: "#212123"` 是写死的深色。

**缺失的 token 族（确认不存在）**：无 `--spacing-*`、无 `--shadow-*`（除 `--lens-shadow` / `--admin-shadow`）、无 `--radius-*`（除 `--radius-panel`）、无 `--placeholder` / `--caption` / `--disabled` / `--inverse`。

### 0.3 必须先修的 4 个真实缺陷（不是审美问题，是 bug）

**缺陷 A —— 反色按钮在 light 主题下文字消失（实测 45 行 / 90 处，30 个文件）**

```tsx
// apps/web/app/[locale]/page.tsx:47  ← 首页主 CTA
className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-4 py-3 text-sm font-semibold text-pg-black rounded-lg"
```
`tailwind.config.ts:14,18` 把 `pg-white` / `pg-black` 写死为 `#FFFFFF` / `#101216`，**不随主题变化**。
Light 主题的 `--panel` 也是 `#ffffff` → 白底 + 白边 + 黑字，边界消失，按钮看起来像未完成的白色方块。
同时出现在 `ui.tsx:18`（**`Button` 的 primary variant 本体**）、`(auth)/login:144`、`(auth)/signup:162`、`(auth)/forgot-password:67`、`(auth)/reset-password:100`、`account:102`、`admin:174`、`pricing:127`、`onboarding/*`、`agent-chat.tsx:535`（**发送按钮**）、`admin-credit-console.tsx:224`、`hyperliquid-market-panel.tsx:261`、`imessage-section.tsx:127`、`api-docs-embed.tsx:503,657`、`backtest-lab.tsx:184,203,207`、`gateway-console.tsx:85,94`、`model-upgrade.tsx:130`、`nav.tsx:311,319`、`portfolio-panels.tsx:19`、`mobile-access-panel.tsx:57`、`live-trading-console.tsx:642`、`news-feed.tsx:210`、`strategy-runtime-console.tsx:93` 等。

**缺陷 B —— Markdown 完全无样式**（本轮投入产出比最高的修复）

```tsx
/* puregamma.tsx:414-420 —— Chat 回答的实际渲染器 */
<article className="pg-report prose prose-invert max-w-none text-sm leading-7
  prose-headings:text-text-pg prose-p:text-text-pg-muted
  prose-li:text-text-pg-muted prose-strong:text-text-pg">
  <ReactMarkdown>{content}</ReactMarkdown>
</article>
```
- `@tailwindcss/typography` **未安装**（`tailwind.config.ts:149` `plugins: []`，`package.json` 无此依赖）→ `prose` / `prose-invert` / 所有 `prose-*:` **产出 0 条 CSS**。
- `.pg-report` 在全仓库只出现 1 次，就是上面这个 class 属性本身，**没有任何 CSS 定义**。
- `ReactMarkdown` 调用**没有 `components={{}}`**，**没有 remark/rehype 插件**（全仓库 `remark-gfm|rehype|typography` 匹配 0）。
- 结果：标题继承正文字号字重、`ul/ol` 被 preflight 重置成没有项目符号没有缩进、`blockquote` 无样式、表格无边框无内距、行内 `code` 与 `<pre>` 只继承了 mono 字体。段落节奏完全靠那个 `leading-7`。
- 代码块**没有 header、没有语言标签、没有 copy 按钮、没有横向滚动容器**。GFM 管道表格不解析，原样输出成文字。

**缺陷 C —— focus 可见性只做了一半**

```css
/* globals.css:914-918 */
[data-visual-style="glass"] :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```
`:focus-visible` 全局只有 **1 条规则**，且**只作用于 glass**。`classic` 风格下全站没有 focus 指示；组件里 `outline-none` 出现 **32 次**。`agent-chat.tsx:534,491` 的 textarea / select 直接 `outline-none focus:border-border-pg-strong`（边框透明度 0.10→0.18），键盘用户几乎看不到焦点。

**缺陷 D —— `/chat` 与 `/chat/[conversationId]` 宽度不一致**

- `/chat`：`nav.tsx:160` `max-w-[1440px]` → `.intelligence-shell{max-width:1180px}`（`globals.css:856`）→ 内容列 `max-w-3xl`（768px），两侧各剩 ~59px。
- `/chat/[conversationId]`：`app/[locale]/chat/[conversationId]/page.tsx:12` **直接渲染 `<AgentChat/>`**，没有 `ChronoSlices`、没有 `IntelligenceShell` → 卡片可到 1392px，内容列两侧各剩 ~165px。
- **同一个聊天，切换路由时内容列左右各变化约 106px。** 并且 `max-w-3xl`（48rem）会随 `:root[data-font-scale]`（14/16/18px，`globals.css:110-112`）在 672 / 768 / 864px 之间跳。

另外还有两个必须清掉的"死代码"类别（完整清单见 §8.6）：
- JSX 里在用但 **CSS 里根本不存在**的类：`.hub-hero`、`.chrono-slice`、`.chrono-decision-stream`、`.portfolio-nav`、`.chronosphere-motion`、`.pg-report`
- 定义但**无人 import** 的组件：`components/ui.tsx` 的 `Card` 和 `Badge`、`components/how-it-connects.tsx`（179 行）、`components/theme/tokens.ts` 与 `lib/theme.ts`（全仓库零引用）

### 0.3b 另外 5 个已确认的缺陷（审计实测，一并修）

**缺陷 E —— `.command-submit` 白字对比度不达标**
```css
/* globals.css:890-894 */
.command-submit { background: var(--accent); color: #fff; font-size: 0.72rem; /* ≈11.5px */ }
```
| 组合 | 实测对比度 | 结论 |
|---|---|---|
| `#fff` on dark `--accent` `#5b8cff` | **3.16:1** | **AA 失败**（11.5px 正文需 4.5:1） |
| `#fff` on light `--accent` `#2f66f5` | 4.84:1 | 勉强通过 |
| light `--negative` `#c2413c` on `--panel-muted` `#f0f1f3` | 4.52:1 | 贴着阈值 |
| light `--muted-2` `#666a73` on `--panel-strong` `#e8eaee` | 4.50:1 | **正好卡在阈值**，而 `globals.css:93-95` 的注释只声称"三个面"达标，`--panel-strong` 是第四个面 |

→ 反色按钮的文字色不能写死 `#fff`。Light 主题主按钮字应该用 `--pg-text-inverse`，并在 token 层保证 ≥4.5:1。

**缺陷 F —— `useHtmlDataset` 永远不会触发（Classic 皮肤的实际 bug）**
`lib/chrono.ts:124-139` 读的是 `el.getAttribute("data-" + name)`，调用方传 `"visualStyle"` → 属性名变成 `data-visualstyle`（浏览器会把 `data-visualStyle` 小写化），而真实属性是带连字符的 **`data-visual-style`**（`lib/visual-style.ts:27`、`app/layout.tsx:39`）。`getAttribute` 恒返回 `null`，`MutationObserver` 永不触发。
后果：`chrono/liquid-surface.tsx:23` 的 `const glass = style !== "classic"` 里 `style` 永远是 `undefined` → **Classic 皮肤下依然套用 glass 的折射边**。
5 个调用点全部受影响：`chrono/liquid-surface.tsx:22`、`chrono/chrono-entrance.tsx:19`、`chrono/chronosphere.tsx:20`、`chrono/chrono-slices.tsx:25`、`terminal/liquid-lens.tsx:16`。

**缺陷 G —— 三处 `AppearanceControls` 状态不同步**
`AppearanceControls` 在 `nav.tsx:221`（侧栏）、`:302`（顶栏桌面）、`:323`（顶栏移动）挂载了三次，但 `theme` 是各自独立的 `useState`，且**没有任何 `storage` 事件监听或自定义事件**。在顶栏切换主题后，侧栏那个按钮的图标（`appearance-controls.tsx:58`）会保持旧值直到刷新。也没有跨标签页同步。

**缺陷 H —— Ocean token 没有 light 变体**
`globals.css:269-281` 的 11 个 `--ocean-*` 只在 `:root`（深色）定义，**没有 `[data-theme="light"]` 覆盖**；而 `lib/visual-style.ts:53` 把 `/dashboard`、`/chat`、`/research`、`/secretary` 都标为 Ocean tier → **light 主题下这 4 个页面渲染的是深色偏向的叠层**。

**缺陷 I —— 原生控件不跟随主题**
全仓库没有 `color-scheme` 声明 → 原生 `<select>` 弹层、滚动条、`input[type=date]` 选择器（`usage-panel.tsx:158,159`）跟随操作系统，不跟随 `data-theme`。Light 主题用户 + 深色操作系统 = 白色面板上弹出深色原生控件。

### 0.3c 对比度实测基线（本轮必须全部清除）

| 组合 | 比值 | 要求 | 位置 |
|---|---|---|---|
| `#fff` on dark `--accent` | **3.16:1** | 4.5:1 | `.command-submit` `globals.css:890` |
| light `--muted-2` `#666a73` on `--panel-strong` `#e8eaee` | **4.50:1** | 4.5:1（临界） | 多处以 9–11px 呈现 |
| light `--negative` `#c2413c` on `--panel-muted` `#f0f1f3` | 4.52:1 | 4.5:1（临界） | Badge danger，`ui.tsx:56` |
| light `bg-pg-white` 按钮 on `--panel` `#ffffff` | 无文字失败，但**面与面零分离** | — | 30 个文件 |

参考（已通过，不要动）：dark `--muted` 7.50 / 6.79 / 6.20 on bg / panel / panel-muted；dark `--muted-2` 6.57 / 5.95 / 5.43；light `--muted` 6.30 / 5.58；light `--admin-accent-ink` 5.91。

**规律：`--muted-2` 是最低对比度的 token，却承载了最小的字号（9–11px）。** 修的时候要么提亮 `--muted-2`，要么禁止它用在 11px 以下。

### 0.4 不要做这些（否则会烧掉一整轮）

- 不要重做硬编码色审计。82 行 hex 里 64 行是品牌资产色，本来就该是字面量，目标是收敛不是归零。
- 不要试图消灭全部 2380 处 border 工具类。目标是把**分隔线**从 border 换成 spacing / hairline，不是全局替换。
- 不要把 `data-visual-style` glass 系统直接删掉 —— `tests/e2e/playwright/visual-style.spec.ts` 依赖它。把它**降级为可选的皮肤层**（见 §4.3）。
- 不要删 `--admin-*` 或 `--ocean-*` token —— 有组件在消费。把它们**收进统一命名空间**，不要重写组件。
- 不要重新发明 `--muted` 之外的第三套灰阶。收敛，不扩张。

---

## 1. 参考对象与借鉴边界

参考：`https://www.deepseek.com/`、`https://chat.deepseek.com/`

**借鉴的是设计系统的结构与数值策略，不是外观。**

可以借鉴：
- 语义 token 的分层结构（static 色阶 → alias 语义 → 组件槽位）
- Light / Dark 的色阶与 surface 分层方式
- border 用透明度而非实色灰线
- hover / active 的 alpha 策略
- 0.5px hairline 与"用 shadow 造边界，而不是 border + shadow 同时叠加"
- 字号必须与行高成对出现
- 极端克制的信息密度

**禁止复制：** logo、icon、品牌插画、文案、CSS class 名、源代码、页面布局源码。不要引入 DeepSeek 蓝作为 PureGamma 的品牌色。

### 1.1 DeepSeek 真实 token 参考值（从其生产 token 表提取，非猜测）

**Light（默认，`:root` 等价）**

| 语义 | 值 | DeepSeek token 名 |
|---|---|---|
| 页面底 | `#ffffff` | `--dsw-alias-bg-base` |
| 抬升面 1 | `#ffffff` | `--dsw-alias-bg-layer-1` |
| 抬升面 2 | `#f5f6f7` | `--dsw-alias-bg-layer-2` / `bg-module-platform` |
| 侧栏底 | `#f9fafb` | `--dsw-specific-sidebar-fill` |
| 输入主面 | `#ffffff` | `--dsw-specific-input-major` |
| 菜单/浮层 | `= layer-3` | `--dsw-specific-menu` |
| 主文字 | `#0f1115` | `--dsw-alias-label-primary` |
| 次文字 | `#61666b` | `--dsw-alias-label-secondary` |
| 三级文字 | `#81858c` | `--dsw-alias-label-tertiary` |
| caption | `#adb2b8` | `--dsw-alias-label-caption` |
| 主按钮底 / 字 | `#0f1115` / `#ffffff` | `--dsw-alias-brand-primary` / `label-primary-foreground` |
| 边框 L1 | `rgba(0,0,0,0.039)` | `--dsw-alias-border-l1` |
| 边框 L2 | `rgba(0,0,0,0.102)` | `--dsw-alias-border-l2` |
| 边框 L3 | `rgba(0,0,0,0.122)` | `--dsw-alias-border-l3` |
| 边框 L4 | `rgba(0,0,0,0.161)` | `--dsw-alias-border-l4` |
| hover | `rgba(38,49,72,0.059)` | `--dsw-alias-interactive-bg-hover` |
| hover solid | `#f1f3f5` | `--dsw-alias-interactive-bg-hover-solid` |
| active | `rgba(38,49,72,0.102)` | `--dsw-alias-interactive-bg-active` |
| 链接 | `#4176e6` | `--dsw-alias-link` |
| 成功 / 危险 / 警告 | `#22c55e` / `#ec1313` / `#f59e0b` | `state-*-primary` |
| 失败态 tint | `#fef2f2` | `--dsw-static-red-50` |
| 成功态 tint | `#e6faed` | `--dsw-static-green-100` |
| 警告态 tint | `#fef5e7` | `--dsw-static-amber-100` |
| 侧栏项 hover / active / active-accent | `#f1f3f5` / `#ebeef2` / `#e4edfd` | `specific-sidebar-nav-item-*` |
| 滚动条 / hover | `#e5e5e5` / `#d4d4d4` | `scrollbar-bg-l1` / `hover-l1` |
| 代码块底 / 头 / 行内码 | `#fafafa` / `#fafafa` / `#fafafa` | `markdown-code-block*` |
| 骨架屏 | `rgba(0,0,0,0.039)` | `bg-skeleton` |
| 遮罩 1 / 2 / 3 | `#0000003d` / `#0000001f` / `#0000007a` | `bg-mask-1/2/3` |

**Dark（`body[data-ds-dark-theme]` 等价）**

| 语义 | 值 | 注意 |
|---|---|---|
| 页面底 | `#151517` | **不是纯黑**，是 graphite（带蓝味的 `neutral-bluish-950`） |
| 抬升面 1 | `#232324` | `neutral-bluish-875` |
| 抬升面 2 | `#2c2c2e` | `neutral-bluish-850` |
| 抬升面 3 | `#353638` | `neutral-bluish-800` |
| 侧栏底 | `#1b1b1c` | `neutral-bluish-900` |
| 输入主面 | `#2c2c2e` | |
| 主文字 | `#fafafa` | **不是 `#fff`** |
| 次文字 | `#cfd3d6` | |
| 三级文字 | `#adb2b8` | |
| caption | `#81858c` | |
| 主按钮底 / 字 | `#fafafa` / `#0f1115` | dark 下主按钮**反色**，不是蓝色 |
| 边框 L1–L4 | `rgba(255,255,255,0.059)` / `0.122` / `0.161` / `0.200` | `0f / 1f / 29 / 33` |
| hover / active | `rgba(255,255,255,0.078)` / `0.141` | |
| 链接 | `#679efe` | dark 下用更亮的蓝 |
| 气泡 / 气泡高亮 | `#2c2c2e` / `#43454a` | |
| 侧栏项 hover / active | `#2c2c2e` / `#43454a` | |
| 滚动条 / hover | `#3c3c3d` / `#545557` | |
| 代码块底 / 头 | `#1b1b1c` / `#2c2c2e` | **比页面更深**，不是更亮 |
| 骨架屏 | `rgba(255,255,255,0.078)` | |

**字体 / 动效 / 阴影（两主题通用，直接抄这个策略）**

```
字体栈  -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB",
        "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif
字号    11/16 · 12/18 · 13/20 · 14/22 · 16/24 · 18/26 · 20/28 · 24/32（px/行高，成对）
字重    正文 400 · 强调 500 · 标题 500（几乎不用 600/700）

阴影    lv1: 0 2px 4px 0 rgba(0,0,0,0.051)
        lv2: 0 4px 12px 0 rgba(0,0,0,0.020), 0 2px 8px 0 rgba(0,0,0,0.039)
        lv3: 0 0 1px 0 rgba(0,0,0,0.200), 0 0 4px 0 rgba(0,0,0,0.020),
             0 12px 32px 0 rgba(0,0,0,0.078)
        stroke: 0 0 0 0.5px var(--border-l4)

抬升面  panel     = stroke + 0 3px 8px rgba(0,0,0,0.031) + 0 0 16px rgba(0,0,0,0.020)
        prominent = stroke + 0 3px 8px rgba(0,0,0,0.039) + 0 0 20px rgba(0,0,0,0.051)
        soft      = stroke + 0 4px 16px rgba(0,0,0,0.031) + 0 0 24px rgba(0,0,0,0.031)
        composer 用 soft

关键规则 浮层（menu / popover / modal / 浮起按钮 / composer）：
        border: 0，只吃 box-shadow 的 0.5px stroke 首层。
        永远不要 "border-l2 + elevation shadow" 同时出现。
        0.5px 是中性边框的统一厚度（按钮 / 输入 / 卡片 / 行分隔 / hr）。
```

---

## 2. 硬性工程规则（本轮必须遵守）

这 12 条是"看到 X 就驳回"级别的规则，写代码和 review 用同一张表：

1. **Token 是颜色的唯一出口。** 组件里只允许出现语义 token。品牌资产色（币种 logo / 法币旗帜）是唯一例外，且必须集中在命名常量里（现状 `global-market-terminal.tsx` 已经这样，保持）。
2. **组件 CSS 里零主题选择器。** 不允许在组件内写 `[data-theme=...]`，也不允许写 `dark:`。Light / Dark 只在 token 表里切换。
3. **一个属性只属于一个命名空间。** 一个 CSS 变量要么是语义 token，要么是皮肤本地变量，不能两个都是。`[data-visual-style="glass"]` 不允许再重写 `--panel`。
4. **中性边框统一 0.5px。** 用 `--pg-hairline: 0.5px`。状态色边框、虚线边框保留 1px。
5. **border 与 elevation shadow 不叠加。** 浮层用 `border: 0` + `box-shadow` 首层 stroke。
6. **字号必须成对写行高。** 禁止裸 `text-[13px]`；只允许 §1.1 的 8 个字号档。
7. **间距 4 的倍数。** 只有 `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64`。
8. **transition 只动 `opacity / transform / background-color / border-color / box-shadow`。** 时长只允许 `120ms`（交互）与 `200ms`（浮层），缓动 `cubic-bezier(0.4,0,0.2,1)`。
9. **圆角只用 3 档**：`--pg-radius-sm: 6px`（小控件）/ `--pg-radius-md: 8px`（输入、按钮、卡片）/ `--pg-radius-lg: 12px`（大面、浮层）。**禁止新增 16 / 18 / 20 / 24px**。药丸只允许真正的状态点与头像。
10. **不得为了分组就加壳。** 优先级：留白 → 排版 → hairline 分隔 → surface → 最后才是带边框的卡片。
11. **每个 `hover:` 必须伴随同等的 `focus-visible:`。** 只做 hover 不做键盘态一律驳回。
12. **禁止 `transition: all`。**

---

## 3. 第一优先级：重建 Token 层

### 3.1 重建 `globals.css` 的结构

把 939 行组织成明确分层的 5 个区块，**顺序不可颠倒**：

```
/* 1. 字体 / 字号 / 动效 / 圆角 / hairline（不随主题） */
/* 2. Light 语义 token（默认，:root） */
/* 3. Dark 语义 token（:root[data-theme="dark"] 覆盖同名变量） */
/* 4. 组件级语义类（.pg-btn / .pg-input / .pg-surface ... 只消费 token） */
/* 5. 皮肤层（glass / ocean），只允许覆盖自己的本地变量 */
```

**重要方向性变更：Light 必须是默认。** 当前是反的（dark 在 `:root`，light 靠覆盖），这导致：
- 没有 `data-theme` 属性时（SSR 首帧）用户看到的是深色；
- 未来加第三主题必须继续叠加。

改成：`:root` = Light 真值；`:root[data-theme="dark"]` = Dark 全表覆盖。

这也正是 DeepSeek 的做法：它的 `body` 是 Light 真值，`body[data-ds-dark-theme]` 覆盖同一批变量名，feature 组件 CSS **零主题选择器**。

### 3.2 语义 token 表（`--pg-*` 命名空间）

在现有 74 个 token 之上**收敛**，不要无限扩张。命名映射如下（左 = 旧，右 = 新）：

```
文字
  --foreground        → --pg-text-primary
  --muted             → --pg-text-secondary
  --muted-2           → --pg-text-tertiary
  （新增）              → --pg-text-placeholder
  （新增）              → --pg-text-disabled
  （新增）              → --pg-text-inverse        ← 反色按钮文字用这个

页面与面
  --background        → --pg-bg-page
  （新增）              → --pg-bg-subtle           ← 次级页面底（侧栏、条纹带）
  --panel             → --pg-surface-1
  --panel-muted       → --pg-surface-2
  --panel-strong      → --pg-surface-3
  （新增）              → --pg-surface-raised      ← 浮层 / composer / popover
  （新增）              → --pg-surface-hover
  （新增）              → --pg-surface-active
  （新增）              → --pg-surface-inverse     ← 反色按钮底（当前是写死的 pg-white）

边框
  --border            → --pg-border-subtle   (目标 ≈ rgba(0,0,0,.06) / rgba(255,255,255,.06))
  --border-strong     → --pg-border-default  (≈ .10 / .12)
  （新增）              → --pg-border-strong   (≈ .16 / .20)
  （新增）              → --pg-border-focus

品牌与状态
  --accent            → --pg-accent          ← 保留 PureGamma 自己的品牌色，不要用 DeepSeek 蓝
  --accent-strong     → --pg-accent-hover
  --accent-soft       → --pg-accent-soft
  --accent-ring       → --pg-focus-ring
  --positive          → --pg-positive  + 新增 --pg-positive-soft
  --warning           → --pg-warning   + 新增 --pg-warning-soft
  --negative          → --pg-danger    + 新增 --pg-danger-soft
  --info              → --pg-info      + 新增 --pg-info-soft

Admin / Ocean（保留，但收进命名空间）
  --admin-accent*     → --pg-admin-accent*      （组件可继续用，但只允许引用 --pg-*）
  --ocean-*           → --pg-ocean-*            + 补 light 变体（§4.2b）
```

**`--pg-*-soft` 是新增的关键能力。** 当前失败/成功提示只能用实色边框（`border-status-negative`），非常刺眼。有了 soft 底才能做 DeepSeek 式的安静状态提示。

### 3.3 旧 token 处理方式（不要大爆炸重写）

`--background` / `--panel` / `--foreground` / `--muted` 等旧名**保留为别名**，一个版本周期：

```css
:root {
  /* 新语义层（唯一真值来源） */
  --pg-text-primary: #0f1115;
  /* … 其余 40 个 … */

  /* 兼容别名：下一个迭代删除。不要在新代码里使用 */
  --foreground: var(--pg-text-primary);
  --background: var(--pg-bg-page);
  --panel: var(--pg-surface-1);
}
```

同时把 `tailwind.config.ts` 里指向旧名的映射改为指向新名，**class 名可以不变**（`text-text-pg` 继续可用），这样 2380 处工具类零改动就迁移到新系统。

### 3.4 Light / Dark 目标色阶（照 §1.1 的策略，用 PureGamma 自己的色相）

不要照抄 DeepSeek 的具体像素值 —— 那会产生"看起来像 DeepSeek"的问题。**照抄的是结构：暗色用带蓝味的 graphite，亮色用带冷灰的白。**

Light 必须具备的视觉关系：
```
--pg-bg-page        略带冷灰（不要纯白）        ← 当前 #f4f4f2 偏暖，改为冷灰
--pg-surface-1      接近白                      ← 当前 #ffffff ✓
--pg-surface-2      非常轻微的灰
--pg-surface-raised 白 + 极轻 shadow
--pg-text-primary   近黑但不是纯黑              ← 当前 #17181c ✓
边框                主要靠 rgba 黑透明度，而不是实色灰线
```
**当前 light 的 `--border: rgba(15,23,42,0.10)` 方向是对的，保留并补齐 3 档。**

Dark 必须具备：
```
--pg-bg-page        深 graphite / 墨蓝黑，不是 #000    ← 当前 #0b0e14 ✓ 方向对
--pg-surface-1/2/3  每级比上一级亮一点点，差异要"几乎看不出但分层成立"
--pg-text-primary   #fafafa 级别的灰白，不是 #fff      ← 当前 --foreground: #eef1f6 ✓
--pg-border-*       rgba(255,255,255,…)
代码块底色           比页面更深，而不是更亮（DeepSeek: block #1b1b1c vs page #151517）
```
**禁止：** `filter: invert()`、纯 `#000` 页面、纯 `#fff` 正文。

---

## 4. 主题与皮肤架构（修缺陷 A / C / E–I + 防闪 + System）

### 4.1 三层收敛

当前有 `data-theme`（2 值）× `data-visual-style`（2 值）× `data-surface-tier`（3 值）× `data-font-scale`（3 值）= 36 种组合，且 glass 层会重写语义 token。收敛为：

| 层 | 属性 | 值 | 谁拥有 |
|---|---|---|---|
| 主题 | `data-theme` | `light` / `dark`（`system` 解析后落地为这两者之一） | token 表 |
| 密度 | `data-font-scale` | `compact` / `default` / `large` | 保留现状 |
| 皮肤 | `data-visual-style` | `glass` / `classic` | **只允许覆盖 `--skin-*` 本地变量，禁止重写 `--pg-*`** |

`data-surface-tier` 保留（`financial` / `ocean` 有真实可读性理由），但它**只能覆盖皮肤变量**。

### 4.2 防闪 + System 支持（一起做，只做一次）

在 `app/layout.tsx` 的 `<head>` 里**扩展现有的 `beforeInteractive` 脚本**（现在 L39 只处理 visual-style），加入主题解析，且必须在首帧之前落地：

```js
// 伪代码，按现有脚本风格写
var pref = localStorage.getItem('pg_theme') || 'system';
var resolved = pref === 'system'
  ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  : pref;
document.documentElement.dataset.theme = resolved;
document.documentElement.dataset.themePreference = pref;
document.documentElement.style.colorScheme = resolved;   // 让原生控件/滚动条跟随
```

同时：
- `<html>` 上补 `suppressHydrationWarning`（已有，L34 ✓）。
- `appearance-controls.tsx` 的 `useEffect`（L23-33）**只负责读取 localStorage 后同步 React state**，不再承担"首次应用主题"的职责。
- **`pg_font_scale` 也要进同一个 pre-paint 脚本** —— 它现在同样只在 `useEffect` 里应用，导致挂载后从 16px 重排到 14/18px。
- **补 `color-scheme`**：脚本里设 `document.documentElement.style.colorScheme = resolved`，CSS 里声明 `:root { color-scheme: light }` / `:root[data-theme="dark"] { color-scheme: dark }`。这一步同时修掉缺陷 I。
- 新增 `prefers-color-scheme` 变化监听：preference 为 `system` 时实时跟随。
- 三态 UI：`System / Light / Dark`。当前是二态开关（`appearance-controls.tsx:57`），**必须改成三态**（同一按钮循环或 segmented control 均可）。
- **修三处实例不同步（缺陷 G）**：把 `theme` / `fontScale` / `visualStyle` 提到一个 Context（或极简 store），并监听 `window` 的 `storage` 事件做跨标签页同步。`nav.tsx:221,302,323` 三处挂载必须同时更新。
- **修 `useHtmlDataset`（缺陷 F）**：`lib/chrono.ts:124-139` 把 `name` 直接拼成 `"data-" + name`，调用方传驼峰 `"visualStyle"` 就会得到错误的属性名。改为在函数内做 camelCase → kebab-case 转换（`visualStyle` → `data-visual-style`），并在 `MutationObserver` 的 `attributeFilter` 里用转换后的名字。**这是 5 个调用点共享的 bug，改一处全修。**

### 4.2b Ocean 补 light 变体（缺陷 H）

`globals.css:269-281` 的 11 个 `--ocean-*` 只在 `:root` 定义，而 `/dashboard`、`/chat`、`/research`、`/secretary` 是 Ocean tier（`lib/visual-style.ts:53`）。给它们补 `[data-theme="light"]` 覆盖；或者（更简单）**让 Ocean 层在 light 主题下退化为 `--pg-*` 语义 token 的静态浅色叠层**，不要硬编码 `--ocean-deep #070b12`。

### 4.3 皮肤层（glass）降级，不要删

`globals.css` 里 70 处 `[data-visual-style="glass"]` 中，**L409-458 那一大段必须删掉** —— 它把 `--panel` / `--border` 重写成 rgba，导致语义 token 失去唯一真值。改法：

```css
/* 现在（错误）：重写语义 token */
:root[data-visual-style="glass"] { --panel: rgba(19,26,38,0.90); --border: …; }

/* 改为：只覆盖皮肤自己的变量 */
:root[data-visual-style="glass"] { --skin-surface-blur: 12px; --skin-surface-fill: …; }
```

然后在组件级语义类里表达，而不是在 token 层：

```css
.pg-surface-1 { background: var(--pg-surface-1); }
[data-visual-style="glass"] .pg-surface-1 {
  background: color-mix(in oklab, var(--pg-surface-1) 90%, transparent);
  backdrop-filter: blur(var(--skin-surface-blur));
}
```

**产品方向说明（需要确认，但默认为此）：** 需求里明确"禁止大面积玻璃毛玻璃"。但 glass 目前是**默认**且 `visual-style.spec.ts` 在测它。所以本轮**不删 glass，但把它从"默认 + token 重写"降级为"可选皮肤 + 局部覆盖"**：保留 `.shell-chrome` / `.shell-rail` / `.liquid` 三处的 `backdrop-filter`（这三处有理由），删除其余 20 余处无差别 blur，删掉 `body` 上的 ambient radial-gradient（L608-620）和 `.chronosphere-field` 的径向渐变（L724-728）。

同时修掉 `.liquid-surface` 只在 glass 下有样式的问题（`globals.css:706` vs base 规则 `:656` 漏了它）→ Classic 皮肤下 `chrono/liquid-surface.tsx:27` 现在渲染出**完全没有样式的 `<section>`**。

### 4.4 Focus（修缺陷 C）

```css
/* 提升到全局，脱离 glass 门控 */
:where(a, button, input, select, textarea, summary, [tabindex]):focus-visible {
  outline: 2px solid var(--pg-focus-ring);
  outline-offset: 2px;
  border-radius: inherit;
}
/* 输入类控件用柔和 ring，不要 2px 硬描边 */
.pg-input:focus-visible,
.pg-input:focus {
  border-color: var(--pg-border-focus);
  box-shadow: 0 0 0 3px var(--pg-focus-ring);
  outline: none;
}
```
- 删除组件里裸用的 `outline-none`（32 处）中**没有**补 focus 样式的那些。
- `agent-chat.tsx:534` 的 textarea 与 `:491` 的 select 是最关键的修复点。
- 焦点环颜色用**品牌 accent 的低 alpha**，不要刺眼蓝圈。当前 `--accent-ring: rgba(91,140,255,0.38)` 偏重，降到 ≈0.20–0.26。

---

## 5. 修反色按钮（缺陷 A：45 行 / 90 处）

新增语义 token：

```css
:root {
  --pg-surface-inverse: var(--pg-text-primary);     /* 反色按钮底 */
  --pg-text-inverse:    var(--pg-bg-page);          /* 反色按钮字 */
}
:root[data-theme="dark"] {
  --pg-surface-inverse: #fafafa;                    /* dark 下主按钮反色为亮色 */
  --pg-text-inverse:    #0f1115;
}
```

然后建立唯一的按钮系统，**把 45 行 `bg-pg-white text-pg-black` 全部替换**：

```tsx
// apps/web/components/ui.tsx —— 扩展现有的 Button（已被 4 个文件 / 13 个调用点消费）
variant: "primary" | "secondary" | "ghost" | "danger"
size:    "sm" | "md" | "lg"

primary   → bg-[var(--pg-surface-inverse)] text-[var(--pg-text-inverse)]
             hover: opacity 0.92 · min-h-9 / 10 / 11
secondary → bg-[var(--pg-surface-2)] text-[var(--pg-text-primary)]
             border-[0.5px] border-[var(--pg-border-default)]
             hover: bg-[var(--pg-surface-hover)]
ghost     → transparent · text-secondary
             hover: bg-[var(--pg-surface-hover)]
danger    → 仅危险写操作：bg-[var(--pg-danger-soft)]
             text-[var(--pg-danger)] border-[0.5px] border-[var(--pg-border-subtle)]
```

统一后顺手删掉 `tailwind.config.ts:14` 的 `pg-white`、`:9-18` 的 `pg-*` 写死色板（`pg-black` / `pg-black-soft` / `pg-panel` / `pg-panel-2` / `pg-panel-3` / `pg-white-soft` / `pg-text` / `pg-muted` / `pg-muted-2`）、`:73-78` 的 legacy `canvas/ink/line/positive/warning/danger`（全站零引用）、`:27` 写死的 `bg-card-hover: "#212123"`。

**补三个 `tailwind.config.ts` 的确切问题：**

1. **`borderRadius` 声明在 `extend` 之外**（`:137-147`）→ 它**整体替换**了 Tailwind 默认刻度，所以 `rounded-xl` = 16px 而不是原生 12px。重写时放回 `extend`，或直接显式定义 3 档（`sm 6 / md 8 / lg 12`）并把全站 `rounded-xl|2xl|3xl` 收敛掉。
2. **`darkMode` 未配置** → 加 `darkMode: ["selector", '[data-theme="dark"]']`。即使禁止写 `dark:`，也要设上，否则将来有人误写会静默绑到操作系统。
3. **`boxShadow` 的 5 个键全是死代码**（`panel` / `card` / `card-hover` / `glow-cyan` / `glow-emerald`，全站零引用），而 `shadow-sm/lg/2xl` 这些 Tailwind 原生值却从 `secretary-console.tsx:25`、`live-trading-console.tsx:370`、`captcha-modal.tsx:57`、`nav.tsx:176` 漏了进来。→ 用本项目自己的 3 档 elevation 替换这 5 个死键，并**把原生 shadow 刻度收紧**（`boxShadow: { sm:'none', DEFAULT:'none', md:'none', lg:'none', xl:'none', '2xl':'none' }` 或整体替换 `theme.boxShadow`），确保浮层阴影只能从 token 来。

`lib/theme.ts` 的 `pgTokens` 是 15 条**纯深色 hex**（`black:"#030303"`、`panel:"#0D0D0D"`、`text:"#EDEDED"`、`muted:"#A3A3A3"`、`muted2:"#737373"`、`positive:"#D9F99D"` …）且**从未被 import** → 删除 `lib/theme.ts` + `components/theme/tokens.ts`。

**注意：不要删 `pg-white` / `pg-black` 就直接跑 —— 先 grep 出全部 45 行（90 处、30 个文件）引用并逐个替换，再删色板，保证 `npx tsc --noEmit` 通过。**

---

## 6. 修 Markdown（缺陷 B，全轮最高投入产出比）

### 6.1 事实

见 §0.3 缺陷 B。一句话：**Chat 的回答目前完全没有排版**，因为 `prose` 系列 class 依赖一个没有安装的插件，而 `.pg-report` 没有任何定义。

### 6.2 修法

**不要引入 `@tailwindcss/typography`** —— 它的默认排版会与 §2 规则 6 的字号系统冲突，且会带进一堆新的 `prose-*` 需要覆盖。手写一份 markdown 样式表：

1. 在 `globals.css` 新增 markdown 区块（或新建 `apps/web/app/markdown.css` 并在 layout 引入），全部消费 `--pg-*` token：
   - `h1` 24/32 · 500；`h2` 20/28 · 500；`h3` 18/26 · 500；`h4` 16/24 · 500
   - `p` 14/22 或 16/24（跟随 `data-font-scale`），段间距 16px
   - `ul/ol` 恢复 `list-style`、`padding-inline-start: 24px`、项间距 8px
   - `blockquote` 左边 2px `--pg-border-strong` + `--pg-text-secondary`
   - `hr` `border-top: var(--pg-hairline) solid var(--pg-border-subtle)`
   - `a` `--pg-accent`，静默无下划线，hover 加下划线
   - `code` 行内：`--pg-surface-2` 底 + `--pg-radius-sm` + mono 13/20
   - `pre` 代码块：`--pg-surface-2` 底（dark 下比 page **更深**）、`--pg-radius-md`、`--pg-border-subtle` hairline、`overflow-x: auto`、`padding: 16px`、mono 13/20
   - `table / th / td`：只有横向 hairline 分隔，表头 `--pg-text-secondary` 12/18 · 500，无竖线、无斑马
2. 在 `puregamma.tsx:414-420` **删掉全部 `prose*` class**，换成 `pg-markdown`，并加 `break-words`。
3. 加 `remark-gfm`（`pnpm -C apps/web add remark-gfm`），让表格 / 删除线 / 任务列表生效。
4. 代码块加**极薄的 header**：语言标签 + copy 按钮。**不要 VSCode 风格的大黑框**，Dark 下也不要与页面断裂的纯黑。参考 `api-docs-embed.tsx:205` 已有的 `overflow-x-auto` + `gateway-console.tsx:96` 已有的 copy 交互，抽成共用组件。

`components/markdown.tsx` 现在只是 7 行的 re-export 且**聊天根本没用它**（只有 `reports-console.tsx:4` 与 `dashboard/page.tsx:6` 用）→ 把新的 `pg-markdown` 渲染器放进这个文件，然后让 `puregamma.tsx:414-420` 和那两处都走同一个组件，消除重复。

全部改动在 `apps/web`，不涉及 `packages/`。

---

## 7. Chat 工作区（本轮最大工程量）

### 7.1 布局：统一宽度（修缺陷 D）

```
Shell                      1440px（保持 nav.tsx:160）
Chat 工作区内容列           统一一个值 → 收进一个共享 class / token
/chat 与 /chat/[id]        两侧留白必须一致
```

- 把 `IntelligenceShell`（`.intelligence-shell{max-width:1180px}`，`globals.css:856`）也应用到 `app/[locale]/chat/[conversationId]/page.tsx`；或者更彻底：**让 `AgentChat` 自己拥有宽度契约**，不再依赖页面级包裹。
- 内容列宽度写成一个 token：`--pg-chat-measure: 48rem`，并在 `data-font-scale` 变化时**不跟随缩放**（当前 672 / 768 / 864px 的跳变是意外的）。用固定 px 或 `clamp()` 固定上下限。
- Composer 与内容列同宽（现状已是 `max-w-3xl`，保持）。
- **确保 composer 在首屏可见**：`/chat` 上 `IntelligenceShell` 的 header（约 190px：eyebrow + `display-lg` `clamp(2.6rem,6vw,4.2rem)` + byline + `mb-8`）把 composer 挤到折线以下（卡片高 `h-[calc(100dvh-7rem)] min-h-[620px]`，`agent-chat.tsx:411`）→ 文档高度 ≈ `100dvh + ~186px`。把 header 收成一行，或让卡片高度基于容器而不是 `100dvh`。
- **新增横向溢出保护**（当前真实缺陷）：`agent-chat.tsx` 里 **0 处** `break-words` / `overflow-x-auto`（只有 `min-w-0` 在 `:429,449,481,483,541`），而祖先有 `overflow-hidden`（`:412`、`:449`）→ 一个长 URL / 长 hash / base64 会被**静默裁掉**，没有滚动条也没有省略号。修法：markdown 容器加 `break-words`，`pre` / `table` 加 `overflow-x-auto`，`StrategyToolResult` 的 3 列网格（`chat-panels.tsx:43`）加 `min-w-0`。注意现有 e2e 守卫（`contrast-audit.spec.ts:129-138` 断言 `scrollWidth <= clientWidth + 1`）因为裁切而**恒为真**，所以这条修复必须配一个新断言（见 §9.3）。

### 7.2 移动端：对话历史必须可达（真实功能缺陷）

`agent-chat.tsx:414/418` 的侧栏是 `hidden … lg:flex`。**低于 1024px 时，整个对话历史、"新对话"按钮（`:423`）以及"删除全部历史"（`:440`）全部消失**，用户只能靠 `/dashboard` 的 "Today activity" 链接（`today-activity.tsx:82`）或手输 URL 回到旧对话。

修法：把历史侧栏做成 `lg` 以下的 Drawer（复用 `nav.tsx:170-210` `MobileNavDrawer` 的模式：`fixed inset-y-3 left-3 z-50 w-80 max-w-[85vw]`、`-translate-x-full → translate-x-0`、`transition-transform duration-200`、scrim `fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden`），入口按钮放在 composer 上方那一行。这不是审美问题，是可用性缺陷，本轮必须修。

### 7.3 常驻 UI 减重

当前 composer 区**恒定渲染 6 行**（`agent-chat.tsx:480-537`）：

| 行 | 位置 | 处理 |
|---|---|---|
| ResearchModeSwitch + 一行模式说明 | `:480-488` | 说明文字删除；开关收进 composer 内部右侧 |
| "Model for this turn" 标签 + `<select>` | `:489-494` | 删标签，改为 composer 内一个轻量 model chip |
| 模型异常提示（条件渲染） | `:497-502` | 保留（只在异常时出现，符合"安静"原则）✓ |
| 高级研究设置折叠卡（带边框） | `:503-530` | 删掉外层边框，改为 composer 内的一个 ghost 按钮 + popover |
| form（attach / textarea / send） | `:531-536` | 重做为 §7.4 |
| footer：模式提示 + `Estimated cost: N Credits` | `:537` | **`Estimated cost: - Credits` 在拿到报价前就渲染，是纯噪音**。改为有报价时才显示，且放进 send 按钮的 tooltip，不要常驻一行 |

侧栏头部 `:419-425` 常驻 `{remaining}/{limit} remaining · {credit_balance} Credits` —— 保留但降权（tertiary 文字，不要与 "PureGamma Agent" 标题同级）。

另外两处常驻噪音：`ocean-shell.tsx:47-57` 的浮动 "Motion / Static" 按钮（`absolute right-2 top-2 z-20`，压在卡片右上角）建议收进设置；`:465-471` 最新回答下方常驻 3 个交叉链接，建议只在用户点开 "sources" 时出现。

**目标：composer 从 6 行降到 2 行。**

### 7.4 Composer 重做

目标形态（DeepSeek 式单容器）：

```
┌─────────────────────────────────────────────┐
│  Ask PureGamma about markets, portfolios…    │   ← 无边框 textarea，
│                                              │      placeholder 用 --pg-text-placeholder
│  [+]  DeepSeek V4.1 Flash ▾        [ Tools ] │  ↑ ← 底层工具行
└─────────────────────────────────────────────┘
                                              ( ↑ )
```

- **一个** raised surface 容器：`background: var(--pg-surface-raised)`，`border: 0`，`box-shadow: var(--pg-elevation-soft)`（0.5px stroke 首层），`--pg-radius-lg`。当前是 **5 层嵌套边框**（OceanShell 边 → `p-1 md:p-1.5` 包裹 → grid 边 → composer `border-t` → textarea 边），必须降到 1 层。
- textarea 本身 `border: 0; background: transparent; outline: none`，focus 交给外层容器的 ring。
- 发送按钮：现在是 `h-14 w-12`（48×56px）的白色方块（`agent-chat.tsx:535`）。改为 32–36px 的圆形/圆角图标按钮，`--pg-radius-md`，静默态用 `--pg-surface-inverse`，disabled 用 `opacity: .35`。busy 时它被 stop 按钮替换（`:535`）—— stop 用 `--pg-danger` 文字但不要实色底。
- attach 按钮 `h-14 w-11` → 32px ghost。
- 附件上限提示（5 个 / 20KB each / 50KB total，`agent-chat.tsx:355-370`）不要常驻，改为超限时才出现在容器内的一行。
- **Thinking / Tools 目前没有任何 UI 控件**（`agent-chat.tsx` 里 `thinking` 只有文案，0 个 state / handler）。如果后端不支持，**不要造假控件**，本轮跳过；如果要做，做成 composer 底行的两个轻量 chip。

### 7.5 消息渲染

现状（`agent-chat.tsx:457`）：
```tsx
user      → "ml-auto max-w-[85%] border border-border-pg-strong bg-bg-panel-muted p-3 text-sm"
assistant → "max-w-full border-l border-border-pg pl-4"
```
- **User 是 1px 实边 + 方角的盒子**（没有 `rounded-*`），与全站 `rounded-lg` 控件语言冲突 → 改为 `--pg-radius-lg` + `--pg-surface-2` + **无边框** + `max-w-[min(85%,42rem)]`。
- Assistant 已经"非卡片化"了 ✓ —— **这个方向是对的，保持**。但要补：
  - 首条 assistant 消息加一个 12px 的角色标识（"PureGamma"），后续消息不加。现在每条消息都打 byline（`:458`），长对话里模型名会重复 N 次。**收敛为：整段对话只在第一条 assistant 上标一次。**
  - 消息级操作（copy / retry）用 `group-hover` + `focus-visible` 出现，常驻 0 个。
- **流式态目前是 `ReportMarkdown content={message.content || "Analyzing..."}`（`:458`）** —— 把 "Analyzing..." 当作正文渲染，是全字号全权重的 markdown 内容。改为安静的 streaming 指示（末尾闪烁 caret 或 3 点），不要用正文占位。
- 载入态 `grid min-h-64 place-items-center` + 旋转图标（`:451`）是一个 ≥256px 的空白块 → 改为局部骨架，保持结构稳定。

### 7.6 Agent 状态 / Tool calls

已经做得不错的部分，保持：
- `AgentStageIndicator`（`agent-stage-indicator.tsx:32-48`）是**小的内联状态行**（~2rem），带 `role="status" aria-live="polite"` ✓ 不要变成大 loading card。
- 计划/证据行（`:473`）也是小行 ✓。

必须修的：
1. **Tool call 失败与成功视觉完全一致**（`:475` + `:258`）：`<span className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs text-text-pg-muted">`，失败时颜色不变、图标不变、无错误文案、无时长、不可展开。→ 失败才突出：`--pg-danger` 文字 + `!` 图标 + 可展开详情。成功态保持安静。
2. **非 strategy 类 tool 结果完全不渲染**（`chat-panels.tsx:36`：只有名字含 `strategy|activation|order_preview` 才返回内容）→ market / quote / news / portfolio 的结果被静默丢弃。至少渲染一个可展开的 "N results" 行。
3. Tool chip 是**追加不清除**的（`:212`），跑到第 10 轮会堆一屏 → 只保留本轮 + 折叠历史。

### 7.7 空状态与错误态

- 空状态（`:452-455`）已经比较克制：eyebrow + h1 + 一行说明 + 4 张 starter card。**4 张卡降到 3 张**，卡片去边框改 `--pg-surface-2` + hover surface。
- 错误态（`:538-552`）渲染在 **composer 区而不是 transcript** —— 位置反了，用户会漏掉。改为 transcript 末尾的内联行：一行 `--pg-danger` 文案 + Retry + Details 折叠。**不要 `System Error 500` / traceback / JSON。** 现有 `lib/chat-errors.ts:103-184` 的文案映射质量不错，保留。
- 计费三态（`refunded` / `settled` / `unknown`，`:547`）保留，`unknown` 时给 `/gateway` 链接 ✓。
- 全站没有 toast 系统，现在是内联 banner。本轮**不要新增 toast**。

### 7.8 无障碍

- 图标按钮用 `title` 而非 `aria-label`：`agent-chat.tsx:415,422,423,433,533,535` → 全部补 `aria-label`。
- 流式回答不在 live region 里（只有 stage row 是）→ 给 assistant 容器补 `aria-live="polite"`，但**注意不要逐 token 播报**（用 `aria-busy` + 完成时一次性播报）。
- `motion-reduce` / `motion-safe` 全站 **0 处**；`animate-spin` 无 reduced-motion 覆盖 → 补。
- `scrollTo({behavior:"smooth"})`（`:159`）无 reduced-motion 分支 → 补。

---

## 8. 信息密度：把 border 换成留白（2380 → 目标 ≤1600）

### 8.1 通用规则

```
优先级：留白 > 排版 > hairline 分隔 > surface > 带边框卡片
```

- 新增 `.pg-divider { border-top: var(--pg-hairline) solid var(--pg-border-subtle) }`，替换同组内的 1px 实边。
- 新增 `.pg-section { display: flex; flex-direction: column; gap: 32px }`（复用现有 `--section-gap` 思路，但收到 3 档：24 / 32 / 48）。
- **不要为了分组就加壳。** 反例：`account/page.tsx` 有 6 个 `ResearchCard` 全部带边框、0 个裸 section。

### 8.2 首页（工程量最小，优先级最低，但缺口明确）

事实：`app/[locale]/page.tsx` 只有 67 行，3 个区块，但：

| 问题 | 位置 | 处理 |
|---|---|---|
| **Hero 区 3 个 CTA** | `page.tsx:47,50,53`（Start Chat / API Quickstart / View pricing） | **降到 2 个**：Primary `Start with Agent`、Secondary `Explore API`。`View pricing` 移到页脚 |
| 卡片内又套一层品牌行 | `page.tsx:32-34`（`border-b` + logo + "PureGamma AI"） | 删除 —— 顶栏已经有 logo 了 |
| 模型公告渲染 3 次 | `page.tsx:36-38`、`model-upgrade.tsx:119-124`、`landing.json:116-117` 页脚轮播（4500ms 自动轮播） | 只保留 model section 那一次；**页脚轮播删除**（自动轮播本身就是噪音） |
| 公告文案与真实状态不一致 | `page.tsx:36`：tone 跟随 catalog，但文案是写死的 "is now available"；catalog 不可用时仍宣称 available，只是变灰 | 文案必须跟随 `availability.state`，否则删掉这个 badge |
| 首页被包在整个产品壳里 | `app/[locale]/layout.tsx:45` 给**每个** locale 路由套 `AppShell` → 首屏有 16 个侧栏项 + plan badge + credits + 5 个外观控件 | 决定：首页要么独立于 AppShell，要么接受它（产品定位问题）。**至少让侧栏在首页默认收起** |
| Hero 标题偏长 | `landing.json:16`："Decide where to take Beta, where Alpha may exist, Long Gamma NAV 1 > 50." | 缩短到一行能读完；术语堆叠是文案问题，不是 UI 问题 |
| 首屏 23 个带边框容器 | 其中 **17 个是 `trading-architecture.tsx` 的 NodeCard**（`text-[0.58rem]` / `text-[9px]`） | 架构图节点去边框，改用 surface + 连接线；`h-[520px]` 固定高（`:116`）在移动端是灾难 |

**目标：首屏 CTA 2 个、带边框容器 ≤6 个、badge ≤2 个、常驻图标 ≤6 个。**
注意首页实际只有 3 个营销区块，但壳层另外贡献约 25 个交互控件（16 个侧栏项 + logo + Bind iMessage + signup/login + 语言 + 4 个外观按钮）。

### 8.3 Model Section（保持 227px 的轻量结构，只换皮）

现状高度 227px（上一轮成果，见 commit `3b8f074e`），结构正确，只改视觉：
- `border border-border-pg` 1px → hairline `--pg-border-subtle`。
- `bg-bg-panel` → `--pg-surface-1`，`rounded-2xl`(20px) → `--pg-radius-lg`(12px)。
- **"Available" 徽章改安静**：当前是 `border + bg-panel + text-status-positive` 的药丸 + `Check` 图标（`model-upgrade.tsx:122-124`，`puregamma.tsx:443`）→ 改成 `● Available`（6px 绿点 + secondary 文字），**只在异常态才用颜色强调**。已有的 `StatusDot`（`puregamma.tsx:145`，`h-1.5 w-1.5 rounded-full`）直接复用。
- 3 个 CTA（`:128-133` 主 CTA + `:138` Gateway + `:142` API）→ 1 个主 CTA + 1 行 tertiary 文字链接。
- `data-model-availability` 属性（`:111`）被 e2e 断言（`model-upgrade.spec.ts:165,218`），**保留不动**。

### 8.4 Admin（约 10%）

事实：`/admin` 稳态渲染 **13 个带边框 tile**，`space-y-5`（20px 节奏），是全站最密的面；而 `/dashboard` 用 `.terminal-panel` + 32–72px 的 `--section-gap`，是最舒展的。**两者必须统一。**

| 问题 | 位置 | 处理 |
|---|---|---|
| Admin nav 是**横向 chip 行**，不是侧栏 | `admin/layout.tsx:48-76`（`border border-border-pg bg-bg-panel p-3 rounded-xl` + `flex flex-wrap`） | 改成纵向分组侧栏；`admin/layout.tsx:55` 的 `const active = activePath === item.href` 是**精确匹配**，`/admin/gateway` 永远点亮不了 `/admin` → 改成前缀匹配 |
| `/admin` 在全局导航里**不存在** | `nav.tsx:37-69` 的 16 项里没有 admin 入口；唯二入口是 `internal/login/page.tsx:33` 的 redirect 和 `/admin` 页内的一张卡 | 给 admin 角色加一项（或至少加在 account 分组） |
| 13 个 tile | `admin/page.tsx:69,86,155,165,167,179`；`admin-credit-console.tsx:161,200,233,244,258` | 降到 ≤7：4 个指标用**裸排版**（数字大、标签小、无框、靠留白分组），不要 4 个 MetricCard |
| 异常不突出 | `admin/page.tsx:82`：`tone` 只作用到 6px 的 `StatusDot`，数字的大小和颜色在 0 与 10000 之间**完全一样** | 有异常时数字本身用 `--pg-warning` / `--pg-danger`，并加一行说明 |
| 指标卡里每个都带同尺寸的 muted `detail` | `puregamma.tsx:134` | 删掉，或降到 caption 且有值时才有 |
| 8/11 个 i18n module key 是孤儿 | `messages/en/admin.json:12-24`，只有 users / reports / stripeWebhookEvents 被引用；`admin.json:8` 的 `subtitle` 无人使用 | 要么接线，要么删除。不要留"承诺了但不存在的面" |
| Admin 表格三套实现 | `pg-table.tsx` 只服务 billing + options；`admin-users-table.tsx` 是 bespoke（表头大写）；`data-source-table.tsx` **根本不是表格**（是卡片网格，9 个 `<dl>` 指标） | 统一到 `pg-table.tsx`：横向 hairline only、表头 `--pg-text-secondary` 12/18、行 hover `--pg-surface-hover`、无竖线、无斑马。三个表格都要有 hover（现在只有 `.workbench` 有，`globals.css:866`） |
| 分页半接线 | `admin/stripe-events/page.tsx:38-42` 解析 `?page=` 但**不渲染分页控件**，且 event type chip 截断到前 8 个；`billing-intents` 既无筛选也无分页；`admin-credit-console` 打印了 `total` 但 `lib/api.ts:1288` 写死 `limit=50` 拿不到后面 | 补齐或隐藏。**不要显示一个用户到达不了的数字** |

已做对的部分，保持：Admin nav 的 active 是 subtle surface（`border-border-pg-strong bg-bg-panel-muted font-semibold`），不是大蓝块 ✓；`admin-users-table.tsx` 的 server-side 分页契约（250ms debounce + `requestRef` stale guard）质量很好 ✓，被 `admin-console.spec.ts:132-170` 锁定，**不要改它的行为**。

### 8.5 Account / Billing / Dashboard

- `account/page.tsx`：6 个 ResearchCard、0 个裸 section → 改成 3 个 section（Identity / Agent / Security），组内用 hairline + 留白。`:106` 是一个约 4KB 的单行 JSX（iMessage 表单），**拆成子组件**。
- `billing/page.tsx`：9 个 ResearchCard + 8 个标题 + 4 个 plan 卡片 → plan 卡片降为一行对比条目，不要 4 个等重卡片。
- `dashboard/page.tsx`：7 个 `.terminal-panel` 用了 32–72px 间距，与 admin 的 20px 冲突 → 统一到 `--pg-space-section: 32px`（或保留 2 档：紧凑 24 / 舒展 40）。

### 8.6 清理死代码（一次性）

| 类别 | 清单 |
|---|---|
| JSX 在用但 CSS 不存在 | `.hub-hero`、`.chrono-slice`、`.chrono-decision-stream`、`.portfolio-nav`、`.chronosphere-motion`、`.pg-report` |
| 定义但无人 import | `components/ui.tsx` 的 `Card`、`Badge`；`components/how-it-connects.tsx`（179 行）；`lib/theme.ts` + `components/theme/tokens.ts`（零引用） |
| 指向不存在的 CSS 变量 | `globals.css:343,362,376` 的 `--bg-panel`、`:363,377` 的 `--border-pg`（**从未定义，无 fallback，声明整体失效**）；`trading-architecture.tsx:44` 的 `var(--text-pg, #9ca3af)` |
| Tailwind 死键 | `boxShadow` 的 `panel` / `card` / `card-hover` / `glow-cyan` / `glow-emerald`；`colors` 的 `canvas` / `ink` / `line` / `positive` / `warning` / `danger`（全部零引用） |
| 死 radius 档位 | `rounded-sm`（0 引用）、`rounded-3xl`（0 引用）、裸 `rounded`（0 引用）→ 与 §2 规则 9 的三档收敛一起处理 |
| 重复 badge 词汇 | `puregamma.tsx:140-142` 的 `Badge`（neutral/info/cyan/emerald/amber/red）与 `ui.tsx:48-62` 的 `Badge`（neutral/positive/warning/danger）→ 合并为一个；`ocean/status-badge.tsx` 是**第三套**（`StatusBadge` / `StatusBadgeWithPulse` / `CapabilityBadge` / `LoadingBadge`）→ 一并收敛 |
| 卡片原语四份 | `ui.tsx:5` `Card`（死）、`puregamma.tsx:61-63` `ResearchCard`/`PGResearchCard`、`globals.css:646` `.terminal-panel`、`globals.css:656` `.liquid`/`.lens-surface` → 收敛为一个 `pg-surface` 语义类 + 2 个变体（flat / raised） |
| 表单原语 | `ui.tsx` 的 `Input`/`Select`/`Field` 只被约 3 个文件使用；**约 30 个文件**手写 `min-h-9/10 border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm … rounded-lg` → 扩展到全部表单 |
| 按钮尺寸无刻度 | 高度散落 `h-9 / h-10 / h-11 / h-14 / min-h-9 / min-h-10 / min-h-11 / 无`，内边距 `px-2 / px-2.5 / px-3 / px-4 / px-5` → §5 的 sm/md/lg 三档统一收口 |
| 缺失的交互原语 | Modal / Dropdown / Tooltip / Popover / Tabs / Toast **全部不存在**：5 处手写 modal（`captcha-modal.tsx:51-52`、`memory-console.tsx:234`、`live-trading-console.tsx:370,903,968`、`nav.tsx:176`）无 portal（`createPortal` 0 处）、无 focus trap、无 Escape 处理、无滚动锁 → 本轮至少抽出一个 Modal/Drawer + 一个 Popover |
| 未使用的 i18n | `landing.json:6-13` 的 `header` 块；`admin.json:8,12-24` 的大部分 |
| 皮肤下未样式化 | `.liquid-surface` 只在 `[data-visual-style="glass"]` 下有样式（`globals.css:706`），base 规则 `:656` 只列 `.liquid, .lens-surface` → Classic 皮肤下渲染出**完全没有样式的 `<section>`** |

---

## 9. 截图与验证

### 9.1 截图（生成到 `.preview-round5/`）

```
home-light.png / home-dark.png
chat-light.png / chat-dark.png
chat-empty-light.png / chat-empty-dark.png
chat-streaming-light.png / chat-streaming-dark.png          ← 新：验证 streaming + tool 状态
admin-light.png / admin-dark.png
gateway-light.png / gateway-dark.png
billing-light.png / billing-dark.png
mobile-home-light.png / mobile-home-dark.png                ← 390×844
mobile-chat-light.png / mobile-chat-dark.png
mobile-chat-drawer-light.png / mobile-chat-drawer-dark.png  ← 新：验证 §7.2 修的侧栏抽屉
```

所有成对截图必须**同一 viewport、同一数据 stub、同一滚动位置**。
现有资产：`.preview-before/`、`.preview-after/`、`apps/web/capture-v41-flash-screenshots.mjs` 可以复用脚本骨架。

### 9.2 浏览器真实检查（不能只看截图）

用 Playwright `evaluate` 读关键节点的 **computed style**，确认真的在用 token：

```
backgroundColor / color / borderColor / borderWidth / boxShadow / fontSize / fontWeight / borderRadius
```

至少覆盖：`body`、`.shell-rail`、`.shell-chrome`、一个 `pg-table` 行、composer 容器、textarea、assistant 消息、`pre` 代码块、一个 dropdown/menu、一个 modal。

### 9.3 新增测试

| 文件 | 断言重点 |
|---|---|
| `tests/e2e/playwright/theme-system.spec.ts` | light / dark / system 三态；刷新后主题保持；**刷新瞬间 `documentElement.dataset.theme` 必须是最终值（防闪回归）**；`colorScheme` 已设置；`data-font-scale` 同样无闪 |
| `tests/e2e/playwright/theme-popover.spec.ts` | dark 下打开 menu / select / dialog / tooltip 不能出现白色；light 下不能出现深色 |
| `tests/e2e/playwright/chat-design.spec.ts` | 内容列宽度在 `/chat` 与 `/chat/[id]` **完全相等**；composer 在 900px 高视口内可见；**长 URL / 长 hash 不被裁切**（这条现在恒为真，因为裁切掩盖了溢出）；assistant 不是卡片；tool 失败与成功视觉不同 |
| `tests/e2e/playwright/markdown-render.spec.ts` | 构造含 h1–h3 / ul / ol / blockquote / table / inline code / code block 的回答，断言**每个元素的 computed `fontSize` / `listStyleType` / `borderTopWidth` ≠ 默认值**（防"prose 没插件"回归） |
| `tests/e2e/playwright/admin-theme.spec.ts` | admin 在 light/dark 都无白底断裂；active nav 前缀匹配生效 |
| `tests/e2e/playwright/mobile-theme.spec.ts` | 390×844 / 430×932 无横向溢出；**chat 历史抽屉可打开并能进入旧对话** |
| `tests/e2e/playwright/hairline-audit.spec.ts` | 中性分隔线 computed `borderTopWidth` ∈ {0, 0.5, 1}，且不存在 `border + elevation shadow` 同时非 0 的浮层 |

### 9.4 扩展现有 `contrast-audit.spec.ts`

它现在**只 `console.log`，不断言**（`:131-138` 只断言了 overflow）。本轮必须：
1. 加 `expect(failures).toHaveLength(0)`。
2. 覆盖范围从 `/zh/chat` 扩到 home / chat / admin / gateway / billing / account × light / dark。
3. 额外覆盖 `placeholder` / `caption` / `--pg-text-tertiary` / field label / disabled。

注意它的合成算法（`:30-38`）已经正确地把 fg 合成到最近的不透明背景上 —— 引入 glass 透明度后**必须保持这个逻辑**，否则会误报。

### 9.5 检查清单（每个 viewport × 每个页面）

Viewport：`390×844`、`430×932`、`1280×800`、`1440×900`、`1920×1080`
页面：Home、Chat（空 / 有对话 / 流式中）、Admin、Gateway、Billing、Notifications、Data Sources

每次必查：
- 主题断裂（dark 下白色 card / light 下黑色 modal）
- 刷新白闪 / 深色闪
- 横向溢出（含长 URL / 长 hash / 宽表格）
- 文本对比度（正文 ≥4.5:1，大字 ≥3:1）
- focus-visible 可见（**含 classic 皮肤**）
- `prefers-reduced-motion` 下无动画
- 布局位移（CLS）

---

## 10. 本轮不修改业务

原则不动：Auth、Billing/Stripe 逻辑、Credits 逻辑、Gateway 路由、Pricing、Agent backend、数据管线、交易、组合计算。

**例外（本轮要动，因为它们是 UI 缺陷）：**
- `apps/web/messages/*/landing.json`、`model-upgrade.json`、`admin.json` 的**文案删除 / 缩短**（§8.2、§8.4）；
- 首页 CTA 数量（§8.2）；
- Admin 分页控件补齐或隐藏（§8.4）—— 只改前端渲染，不改后端契约（`apps/api/services/pagination.py` 已提供 `total/limit/offset/page/has_more`，直接用）。

若发现后端 bug：**单独记录到 `BACKEND_BUGS_ROUND5.md`，不要顺手重构。**

---

## 11. 执行顺序（按依赖关系，不要并行乱改）

```
Phase 0  审计（只读，不改 CSS）
         产出 UI_THEME_AUDIT.md：
           - 74 个 token 的分类与归属（146 行声明 / 74 个名字）
           - 2380 / 324 / 140 / 171 / 82 / 13 / 8 的分布表
           - §0.3 + §0.3b 九个缺陷的复现步骤
           - 组件级硬编码色的真实违规清单（预期约 3 个，不要凑数）
           - 旧 token → 新 token 的完整映射表（逐行，可核对）
         产出 UI_DENSITY_AUDIT.md：
           - 每个页面的 卡片数 / 常驻 badge 数 / 主 CTA 数 / 常驻 UI 元素数
           - 目标值（§8 已给）与实际值的差
         产出 HARDCODED_COLOR_AUDIT.md 的 before 列（82 hex 行 / 13 rgba 行 / 8 调色板行）

Phase 1  Token 层（globals.css 重排 + 别名 + tailwind.config 指向新名
                   + 三个 config 修复：borderRadius 放回 extend、darkMode selector、删死 shadow/颜色键）
         验收：tsc 通过、页面视觉不变（因为别名指向同样的值）
         这是一次"零视觉差异重构"，用来把地基换掉

Phase 2  主题引擎（防闪脚本含 font-scale + System 三态 + color-scheme
                   + 全局 focus-visible + 皮肤层降级 + 缺陷 F/G/H）
         验收：theme-system.spec + 手动刷新无闪

Phase 3  反色按钮（45 行替换 + 按钮系统统一 + 删死色板 + 缺陷 E 对比度）  ← 用户可见的第一个变化
         验收：light/dark 下所有主 CTA 有清晰边界

Phase 4  Markdown（手写样式表 + remark-gfm + 代码块 header）
         验收：markdown-render.spec

Phase 5  Chat 工作区（宽度统一 → composer 重做 → 移动端抽屉 → 消息态 → tool 失败态 → 溢出保护）
         验收：chat-design.spec + mobile-theme.spec

Phase 6  Admin（侧栏 + 前缀匹配 + 密度 + 表格统一 + 分页）
         验收：admin-theme.spec

Phase 7  首页与其余页面密度（CTA 降 2、删重复公告、架构图去边框、卡片换留白）
         验收：UI_DENSITY_AUDIT.md 的目标值达成

Phase 8  截图 + 对比度全量 + 死代码清理（含未定义变量引用）+ 交付报告
```

每个 Phase 单独提交，commit message 用仓库现有的 `feat(web):` / `fix(web):` / `refactor(web):` 风格。

---

## 12. 施工前的 Git 保护（第一步就做）

```bash
git status                # 当前有 17 个 modified + 大量 untracked
git branch --show-current # main
git rev-parse HEAD        # cf8535ee3234f2ebab25f2e96b23c55d6c7a57c2
git log --oneline -20
```

**必须保护的未提交 WIP（其他工程师正在进行，不要覆盖）：**

```
M apps/api/routers/auth.py                       ← X Login 后端
M apps/api/routers/email_auth.py
M apps/api/routers/imessage_agent.py
M apps/api/main.py
M apps/api/config.py
M apps/web/app/[locale]/(auth)/login/page.tsx    ← X Login 前端
M apps/web/app/[locale]/(auth)/signup/page.tsx
M apps/web/app/[locale]/account/page.tsx         ← 同时是本轮 §8.5 的目标文件
M apps/web/messages/en/common.json               ← i18n WIP
M apps/web/messages/zh/common.json
M packages/database/models.py
M packages/database/session.py
M packages/notifications/dispatcher.py
M packages/workers/scheduler.py
M packages/workers/tasks.py
M tests/security/test_production_configuration.py
M scripts/validate-production-env.py
M deploy/production.env.example
?? apps/api/routers/x_auth.py                    ← X Login 新增
?? apps/api/routers/x_bot.py
?? apps/api/services/x_bot_service.py, x_inbound_service.py, inbound_agent_service.py
?? apps/web/app/[locale]/auth/x/                 ← X Login 回调
?? apps/web/components/x-logo.tsx
?? packages/notifications/x_provider.py
?? docs/X_AUTH_AND_BOT.md
?? scripts/x_bot_preflight.py, stage_index_edits.py
```

**明令禁止：** `git add .`、`git reset --hard`、`git checkout -- .`、强推、任何会把上述文件回滚的操作。

**推荐做法：** 开工前为本轮建分支 `git switch -c ui/round5-design-system`，让 X Login 的 WIP 留在工作区不动。

**特别注意：** `apps/web/app/[locale]/account/page.tsx` 同时在 WIP 列表和本轮改动清单里 → **改它之前先和做 X Login 的人对齐**，或者本轮先跳过它，等 X Login 落地再回来。

---

## 13. 构建与测试命令（本仓库的准确路径，无根 package.json）

```bash
# 全部在 apps/web 目录下执行（仓库根目录没有 package.json）
cd apps/web

npx tsc --noEmit          # 本轮实测 exit 0，必须保持
pnpm lint                 # = next lint
pnpm build                # = next build
pnpm test:e2e             # = playwright test
```

Playwright 配置事实（`apps/web/playwright.config.ts`）：
- `testDir: "../../tests/e2e/playwright"` → **测试文件写在仓库根的 `tests/e2e/playwright/`**
- `webServer.command` 自动起 `next dev --port 3000`，`NEXT_DIST_DIR=.next-playwright`，`NEXT_PUBLIC_API_URL=/__dev-api`，`REQUIRE_AUTH=false`，`DEV_API_PROXY_TARGET=https://api.puregamma.ai`
- `reuseExistingServer: true` → 本地已有 3000 端口服务时会复用
- 两个 project：`chromium`（Desktop Chrome）与 `mobile-chrome`（Pixel 5）
- 新增 mobile 视口测试时，用 `test.use({ viewport: { width: 390, height: 844 } })` 覆盖

Windows 提示：`webServer.command` 已经处理了 `set "KEY=VALUE" &&` 的空格陷阱，**不要改它**。

---

## 14. Definition of Done

全部达成才算这一轮完成。

**DESIGN SYSTEM**
- [ ] `globals.css` 按 §3.1 的 5 层结构重排，Light 为 `:root` 默认，Dark 为全表覆盖
- [ ] 语义 token 表建立，旧名保留为别名（零视觉差异）
- [ ] 三档圆角 + 三档边框 + 三档阴影，无新增 16 / 18 / 20 / 24px 圆角
- [ ] 中性边框统一 hairline；浮层不带 border
- [ ] 按钮系统统一（primary / secondary / ghost / danger × sm / md / lg），页面不再自创按钮
- [ ] 表单系统统一
- [ ] `tailwind.config.ts` 的 `pg-*` 写死色板 + legacy 六色 + `bg-card-hover` + 5 个死 shadow 键已删除，`borderRadius` 已放回 `extend`，`darkMode: ["selector", '[data-theme="dark"]']` 已设置
- [ ] `npx tsc --noEmit` 通过

**THEME**
- [ ] Light / Dark 各自独立设计（不是反色）
- [ ] System / Light / Dark 三态
- [ ] 刷新无闪（pre-paint 脚本同时覆盖 `data-theme` **和** `data-font-scale`）
- [ ] 主题持久化
- [ ] `color-scheme` 已设置（CSS + 脚本，缺陷 I）
- [ ] **glass 皮肤不再重写语义 token**
- [ ] 所有 popover / modal / dropdown / select / tooltip 两主题正确
- [ ] 全站 focus-visible（含 classic 皮肤）
- [ ] 三处 `AppearanceControls` 同步 + 跨标签页同步（缺陷 G）
- [ ] `useHtmlDataset` 属性名已修正，Classic 皮肤不再误用 glass 折射边（缺陷 F）
- [ ] Ocean token 已补 light 变体（缺陷 H）
- [ ] `--bg-panel` / `--border-pg` 两个未定义变量引用已清除
- [ ] `.liquid-surface` 在 Classic 皮肤下有样式
- [ ] `.command-submit` 白字对比度 ≥4.5:1（缺陷 E）

**CHAT**
- [ ] `/chat` 与 `/chat/[id]` 内容列宽度完全一致
- [ ] composer 折线以上可见
- [ ] composer 从 5 层边框降到 1 层，常驻行数 6 → 2
- [ ] **markdown 真的有样式**（标题 / 列表 / 引用 / 表格 / 代码 / 行内码）
- [ ] 代码块有薄 header（语言 + copy），非 VSCode 大黑框
- [ ] assistant 非卡片化（保持）+ 模型名不再每条消息重复
- [ ] streaming 不再把 "Analyzing..." 当正文
- [ ] **tool 失败与成功视觉不同**
- [ ] 非 strategy tool 结果不再静默丢弃
- [ ] 长 URL / 长 hash 不被静默裁切
- [ ] **移动端可访问对话历史（抽屉）**
- [ ] 错误态在 transcript 内，文案是 `Couldn't load… / Retry / Details`
- [ ] 空状态 ≤3 张 starter card

**ADMIN**
- [ ] 与主站共享设计系统（同一 surface / 同一间距节奏）
- [ ] Admin 导航改为侧栏 + 前缀匹配 active
- [ ] `/admin` 从全局导航可达
- [ ] 带边框 tile 13 → ≤7
- [ ] 表格统一到 `pg-table`，横向 hairline，行 hover
- [ ] 有异常时**数字本身**变色
- [ ] 分页控件与真实可达数据一致（不显示到达不了的数字）
- [ ] 正常状态安静（绿点即可，不要大绿徽章）

**HOME**
- [ ] 首屏 CTA ≤2
- [ ] 模型公告只出现 1 次，且文案跟随真实状态
- [ ] Model section 保持 227px 级轻量 + hairline + 安静 Available
- [ ] 架构图节点去边框，移动端可用
- [ ] 带边框容器 ≤6

**ACCESSIBILITY**
- [ ] WCAG AA：正文 ≥4.5:1，大字 ≥3:1，`contrast-audit.spec` **有断言且失败数 = 0**
- [ ] §0.3c 的 3 个失败 / 临界组合全部修掉
- [ ] placeholder / caption / label / disabled 全部达标，且 `--muted-2` 不再用于 11px 以下
- [ ] 键盘可达，focus 可见
- [ ] 图标按钮用 `aria-label` 而非 `title`（`agent-chat.tsx:415,422,423,433,533,535`）
- [ ] 流式回答进入 live region，但不逐 token 播报
- [ ] `prefers-reduced-motion` 全覆盖（含 `animate-spin` 与 `scrollTo({behavior:"smooth"})`）

**RESPONSIVE**
- [ ] 390 / 430 / 1280 / 1440 / 1920 全部无横向溢出

**BUILD**
- [ ] `npx tsc --noEmit` exit 0
- [ ] `pnpm lint` 干净
- [ ] `pnpm build` 成功
- [ ] Playwright 全绿（含 §9.3 新增的 7 个 spec）
- [ ] 截图全部产出到 `.preview-round5/`
- [ ] 死代码清理完成（§8.6）

---

## 15. 最终交付报告（不允许写"优化了一些 UI"）

必须包含：

**1. Before / After** —— 至少 5 组同 viewport 对照（home / chat / chat-empty / admin / mobile-chat），light + dark 各一份。

**2. Design Tokens** —— Light 与 Dark 的完整语义 token 表（实际值，不是"见代码"）。标注哪些是新增、哪些是重命名、哪些是别名。

**3. 缺陷修复证据** —— §0.3 / §0.3b 的 **A–I 九个缺陷**，每个给 before / after 的**可验证数字**：

```
缺陷 A：before = 45 行 / 90 处 bg-pg-white|text-pg-black 写死反色（30 个文件）| after = 0 处，Button 统一
缺陷 B：before = prose* 产出 0 条 CSS | after = pg-markdown N 条规则，markdown-render.spec 覆盖 6 类元素
缺陷 C：before = focus-visible 规则 1 条且仅 glass | after = 全局 1 条 + 表单 ring，classic 已覆盖
缺陷 D：before = /chat 内容列两侧各约 59px，/chat/[id] 各约 165px | after = 两侧均 Npx
缺陷 E：before = #fff on dark --accent = 3.16:1（AA 失败）| after = N:1（≥4.5）
缺陷 F：before = useHtmlDataset 属性名恒 null，Classic 皮肤误用 glass 折射边 | after = 5 个调用点正确响应
缺陷 G：before = 3 处 AppearanceControls 各自 useState、无 storage 监听 | after = 单一来源 + 跨实例/跨标签页同步
缺陷 H：before = 11 个 --ocean-* 无 light 变体，4 个 Ocean 路由 light 下偏暗 | after = 已补
缺陷 I：before = color-scheme 声明 0 处 | after = CSS + pre-paint 脚本各 1 处
```

**4. Component Migration** —— Button / Input / Card / Table / Modal / Popover / Badge / Chat / Admin 各自的：旧实现位置 → 新实现位置 → **调用点数量（before → after）**。重点报三个收敛数字：
- 原始 `<button>` 140 行 → `<Button>` 组件调用点 13 → ?
- 手写表单控件约 30 个文件 → `Input` / `Select` / `Field` 调用点 ?
- `Badge` 三套词汇 → 1 套，调用点 ?

**5. 密度指标** —— 逐页面给出 before → after 的表格：带边框容器数、常驻 badge 数、主 CTA 数、常驻 UI 元素数、border 工具类出现次数（全站 2380 → ?）。

**6. 截图路径** —— 全部列出。

**7. Contrast** —— 实际失败数。**目标 0**；若非 0，逐条列出（元素、比值、要求值、前景 / 背景色）。

**8. Responsive** —— 每个 viewport × 每个页面的结果。

**9. Build / Test** —— 准确数字：tsc、eslint warnings/errors、build 时长与包体积变化、Playwright passed / failed / skipped。

**10. Unfinished** —— 明确列出没做完的、为什么、建议下一轮做什么。**不要隐藏。**

**11. Backend bugs found** —— 单独 `BACKEND_BUGS_ROUND5.md`，不在本轮修。

---

## 16. 最终目标

PureGamma.ai 不应该"看起来像 DeepSeek"。

用户应该产生相似的感觉：

> 打开页面时：**安静。**
> 开始使用时：**直接。**
> 复杂功能出现时：**有层次。**
> 没有操作时：**没有任何东西抢注意力。**
> 深色和浅色：**不是换颜色，而是同一个设计系统的两个完整表达。**

PureGamma 的差异来自 **Financial Data / Portfolio / Agent / Research / API Gateway**，
不来自 **更多 Card / 更多 Badge / 更多颜色 / 更多说明文字**。

禁止的视觉套路：大面积 gradient、无差别毛玻璃、neon、glow、超大圆角卡片、彩虹 icon、emoji、满屏 status badge、所有模块 card 化、纯黑暗色、纯白亮色、大阴影、蓝色 everywhere。

最终判断标准：

> **"像一个真正成熟的 AI Investment Workspace，而不是一个套了金融皮肤的 SaaS Dashboard。"**

---

### 附：本轮优先级权重

| 优先级 | 占比 | 内容 |
|---|---|---|
| P0 | 20% | Token 层重建 + Tailwind config 三处修复（radius / darkMode / 死键） |
| P0 | 20% | **Markdown 渲染**（投入产出比最高，Chat 是产品核心，目前回答完全无样式） |
| P0 | 15% | 主题引擎（防闪 / System / focus / color-scheme）+ 反色按钮缺陷 A + 缺陷 E/F/G/H/I |
| P1 | 25% | Chat 工作区（宽度统一 / composer / 移动端抽屉 / tool 失败态 / 溢出保护） |
| P2 | 10% | Admin（侧栏 / 密度 / 表格 / 分页 / 异常强调） |
| P3 | 5% | 首页与其余页面密度、死代码清理 |
| P3 | 5% | 截图 / 视觉回归 / 交付报告 |

### 附：为什么"逐项改 CSS"是错的

审计结论：这个仓库**并不缺 token**（146 行声明、74 个 token、791 行 text token 引用、`dark:` 变体 0 次）。
它缺的是**唯一真值**和**收敛的刻度**：

- 五套 token 体系（基础 / admin / ocean / glass / liquid）里，glass 那一层会**重写语义 token**，使 `--panel` 不再是真值；
- 十档圆角、六套阴影配方、140 行重复按钮字符串、三套 badge 词汇、四套卡片原语；
- 主题开关是 hydration 之后才生效的，所以"看起来是主题问题"的现象（闪、状态不同步、原生控件不跟随）本质是**架构问题**。

所以本轮的顺序不能颠倒：**先建立唯一真值 → 再收敛刻度 → 最后才动视觉。**
如果反过来先调颜色，你会在 5 个体系之间来回打架，一周后回到原点。

DeepSeek 的经验在这里最值得学的不是它的色值，而是它的两条规则：

> 1. 明暗只在 token 表里发生，feature 组件 CSS **零主题选择器**；
> 2. 浮层的边界由 **0.5px hairline stroke 作为阴影首层**提供，永远不与 `border` 叠加。

这两条规则能让上面所有"体系打架"的问题在结构上无法再发生。PureGamma 当前在规则 1 上已经做得很好（`dark:` 0 次），
差的是把 token 表本身收敛成唯一真值；规则 2 则完全没有采用（2380 处 border 工具类、6 套阴影配方）。
把这两条落地，PureGamma 就不需要"像 DeepSeek"——它会自己长成一个成熟的 AI Investment Workspace。
