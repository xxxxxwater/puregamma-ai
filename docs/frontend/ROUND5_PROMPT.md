# PureGamma.ai 第五轮 UI / UX 升级 — 执行提示词（已按本仓库校准）

> 把本文件整份交给主开发。文中每个数字都来自对
> `C:\Users\Administrator\Desktop\puregamma.ai` 的实际扫描（HEAD `cf8535ee`），
> 不是估算。配套阅读：`docs/frontend/UI_THEME_AUDIT.md`、
> `docs/frontend/UI_DENSITY_AUDIT.md`、`docs/frontend/HARDCODED_COLOR_AUDIT.md`。

---

## 0. 你的角色与这一轮的唯一目标

你是 PureGamma.ai 的 Principal Product Designer + Staff Frontend Engineer。

**这一轮不加功能、不改业务、不堆页面。只做一件事：**

> 重建 Light / Dark 双主题设计系统，让两者成为**同一套设计系统的两个完整表达**，
> 并把 Chat 做成真正的 AI 工作区。

借鉴对象是 DeepSeek 官网 / chat 的**设计系统结构与密度哲学**，不是它的外观。

**禁止复制**：logo、icon、品牌插画、文案、CSS class 名、源代码、页面布局源码。
**禁止**把 DeepSeek 的品牌蓝当作 PureGamma 的品牌色。

最终产品必须明显是 **PureGamma.ai — AI Investment Workspace**。

---

## 1. 先读这三份实测审计（已产出，不要重做）

| 文件 | 内容 |
| --- | --- |
| `docs/frontend/UI_THEME_AUDIT.md` | token 结构、主题引擎、10 个已确认缺陷（含复现位置） |
| `docs/frontend/UI_DENSITY_AUDIT.md` | 密度计数、每页卡片数、Chat 常驻元素、垂直预算 |
| `docs/frontend/HARDCODED_COLOR_AUDIT.md` | 87 处 hex 的逐文件归属与删除清单 |

**其中 10 个缺陷是 bug，不是审美问题，必须修。** 见 `UI_THEME_AUDIT.md` §4 的
D1–D10。优先级最高的是 D1（反色按钮）、D2（Markdown 无样式）、D5（移动端
无法访问历史）、D4（两条 chat 路由宽度不一致）。

---

## 2. 事实基线（直接引用，不要重新测量）

### 2.1 仓库与工具链

| 项 | 值 |
| --- | --- |
| 前端 | Next.js 14.2.35 App Router，`apps/web`，React 18.3.1，Tailwind 3.4.17 |
| 唯一 CSS 文件 | `apps/web/app/globals.css`，**940 行 / 211 个规则块** |
| 自定义属性 | **146 条声明 / 74 个不同名字** |
| 主题默认 | **Dark 在 `:root`**，light 靠 `:root[data-theme="light"]` 覆盖 |
| 主题存储 | `localStorage.pg_theme`，仅 `"dark"` / `"light"` |
| `data-visual-style` vs `data-theme` | **70 : 18** — 皮肤层的权重远大于主题层 |
| 构建命令 | 全部在 `apps/web` 下：`npx tsc --noEmit`、`npx next lint`、`npx next build`、`npx playwright test`（仓库根没有 package.json） |
| Playwright | `testDir: ../../tests/e2e/playwright`；webServer 自起 `next dev --port 3000`，`NEXT_PUBLIC_API_URL=/__dev-api`、`REQUIRE_AUTH=false`、`DEV_API_PROXY_TARGET=https://api.puregamma.ai`、`reuseExistingServer: true`；两个 project：`chromium`、`mobile-chrome` |
| Windows 注意 | `playwright.config.ts` 的 `set "KEY=VALUE" && …` 写法修过一个真实 bug（尾随空格让 `REQUIRE_AUTH` 变成 `"false "`，中间件永不匹配）。**不要改回 `set K=V&&`** |

### 2.2 已有的正确做法 —— 明确不要重做

- **`dark:` 变体只有 1 处。** 主题纪律已经建立，这一轮的任务是让 token 表可信，
  不是建立"用变量"的习惯。
- **967 处 `text-text-pg*`** —— 颜色没有在组件里硬编码。
- **`app/` 目录几乎没有硬编码色** —— 纪律在最关键处最强。
- **Agent 状态行与 tool chip 已经是小内联行**，不是整屏 loading。保持。
- **assistant 消息已经非卡片化**（左边框 + 内距）。保持这个方向。
- **`admin-users-table.tsx` 已有服务端筛选/分页 + stale-response 防护**，
  被 `admin-console.spec.ts` 锁定。**不要改它的行为。**
- **上一轮已修 4 个 token 的对比度**（深色 `--muted-2`、浅色 `--positive`、
  `--warning`）。只修剩下的 3 处临界值（D10），不要推翻已有的。

### 2.3 需要纠正的三条常见误判（避免踩空）

| 常见说法 | 本仓库实际 |
| --- | --- |
| "有 2380 处 border 工具类" | **818**（目标 ≤450） |
| "表单原语几乎没人用，约 30 个文件手写" | `<Input>` 55 次、`<Field>` 39 次、`<Select>` 13 次，**都来自 `components/ui.tsx`**。真实重复是 **28 处手写输入框字符串 / 14 个文件** |
| "`--accent` 在使用之后才定义" | 定义 566 行、首次使用 610 行，**顺序正确** |

---

## 3. 十一个硬性工程规则（写成 review 清单，违反即驳回）

1. **Token 是颜色的唯一出口。** 组件里只允许语义 token。唯一的字面量例外是品牌资产色
   （币种 logo / 法币旗帜），且必须集中在一个具名常量里
   —— `global-market-terminal.tsx` 现在就是这么做的，保持。
2. **组件 CSS 里零主题选择器。** 不允许在组件里写 `[data-theme=…]`，也不允许写 `dark:`。
   Light / Dark 只在 token 表里切换。
3. **一个属性只属于一个命名空间。** 一个 CSS 变量要么是语义 token，要么是皮肤本地变量，
   不能两者都是。**`[data-visual-style="glass"]` 不允许再重写 `--panel` / `--border`**
   （这是 D 类结构缺陷的根源，见 §5.3）。
4. **中性边框统一 0.5px hairline**（`--pg-hairline: 0.5px`）。状态色边框与虚线保留 1px。
5. **border 与 elevation shadow 不叠加。** 浮层用 `border: 0` + shadow 首层 stroke。
6. **字号必须成对写行高。** 只允许 8 档：`11/16 12/18 13/20 14/22 16/24 18/26 20/28 24/32`。
   禁止裸 `text-[13px]`。
7. **间距只用 4 的倍数**：4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64。
8. **transition 只动** `opacity / transform / background-color / border-color / box-shadow`，
   时长只允许 120ms（交互）与 200ms（浮层），缓动 `cubic-bezier(0.4,0,0.2,1)`。
   **禁止 `transition: all`。**
9. **圆角只用 3 档**：`--pg-radius-sm: 6px` / `--pg-radius-md: 8px` / `--pg-radius-lg: 12px`。
   禁止新增 16 / 18 / 20 / 24px。药丸只允许状态点与头像。
10. **不得为了分组就加壳。** 优先级：留白 → 排版 → hairline 分隔 → surface → 最后才是带边框卡片。
11. **每个 `hover:` 必须配同等的 `focus-visible:`。** 只做 hover 不做键盘态一律驳回。

---

## 4. 第一优先级：重建 token 层（零视觉差异重构）

### 4.1 重排 `globals.css` 为固定 5 层，顺序不可颠倒

```
/* 1. 字体 / 字号 / 动效 / 圆角 / hairline（不随主题） */
/* 2. Light 语义 token（默认，:root） */
/* 3. Dark 语义 token（:root[data-theme="dark"] 覆盖同名变量） */
/* 4. 组件级语义类（.pg-btn / .pg-input / .pg-surface …，只消费 token） */
/* 5. 皮肤层（glass / ocean），只允许覆盖自己的本地 --skin-* / --pg-ocean-* 变量 */
```

**方向性变更：Light 必须成为 `:root` 默认。**

当前是反的，直接导致两个已确认现象：
- SSR 首帧没有 `data-theme`，所以**每个 light 用户每次刷新都先看到深色**；
- 加第三个主题只能继续叠加覆盖。

DeepSeek 的做法就是这样：body 是 Light 真值，暗色覆盖同一批变量名，
功能组件 CSS 零主题选择器。

### 4.2 语义 token 命名空间 `--pg-*`

在现有 74 个名字之上**收敛**，不要扩张。映射（左 = 旧名，右 = 新名）：

```
文字
  --foreground   → --pg-text-primary
  --muted        → --pg-text-secondary
  --muted-2      → --pg-text-tertiary
  （新增）        → --pg-text-placeholder
  （新增）        → --pg-text-disabled
  （新增）        → --pg-text-inverse        ← 反色按钮文字，修 D1 的关键

页面与面
  --background   → --pg-bg-page
  （新增）        → --pg-bg-subtle           ← 侧栏 / 条纹底
  --panel        → --pg-surface-1
  --panel-muted  → --pg-surface-2
  --panel-strong → --pg-surface-3
  （新增）        → --pg-surface-raised      ← 浮层 / composer / popover
  （新增）        → --pg-surface-hover
  （新增）        → --pg-surface-active
  （新增）        → --pg-surface-inverse     ← 反色按钮底，替代写死的 pg-white

边框
  --border        → --pg-border-subtle  （目标 ≈ rgba(0,0,0,.06) / rgba(255,255,255,.06)）
  --border-strong → --pg-border-default （≈ .10 / .12）
  （新增）         → --pg-border-strong  （≈ .16 / .20）
  （新增）         → --pg-border-focus

品牌与状态
  --accent        → --pg-accent          ← 保留 PureGamma 自己的品牌色
  --accent-strong → --pg-accent-hover
  --accent-soft   → --pg-accent-soft
  --accent-ring   → --pg-focus-ring      ← 把 alpha 从 0.38 降到 ≈0.20–0.26，避免刺眼蓝圈
  --positive      → --pg-positive  + 新增 --pg-positive-soft
  --warning       → --pg-warning   + 新增 --pg-warning-soft
  --negative      → --pg-danger    + 新增 --pg-danger-soft
  --info          → --pg-info      + 新增 --pg-info-soft

现有专用族（保留，但收进命名空间）
  --admin-*  → --pg-admin-*     （组件继续用，只允许引用 --pg-*）
  --ocean-*  → --pg-ocean-*     + 必须补 light 变体（D8）
```

`--pg-*-soft` 是新增的关键能力：当前状态提示只能用实色边框
（`border-status-negative`）表达，非常刺眼；有了 soft 底才能做安静的状态提示。

### 4.3 旧名保留为别名（一个版本周期）

```css
:root {
  /* 唯一真值来源 */
  --pg-text-primary: …;
  /* 兼容别名：下一轮删除。新代码禁止使用 */
  --foreground: var(--pg-text-primary);
  --background: var(--pg-bg-page);
  --panel: var(--pg-surface-1);
}
```

同时把 `tailwind.config.ts` 里指向旧名的映射改指新名，**class 名不变**
（`text-text-pg` 继续可用），这样 818 处 border 工具类与 967 处 text 工具类
**零改动**就迁移到新系统。

> 依据：DeepSeek 自己就同时维护两套命名空间（`--ds-*` 83 个 与 `--dsw-*` 158 个）。
> 别名层是成熟做法，不是偷懒。

### 4.4 修 `tailwind.config.ts` 三处

1. `borderRadius` **在 `extend` 之外**，所以它整体替换了 Tailwind 默认刻度，
   每档都比原生大一档（`lg`=12px 而非 8px，`xl`=16px 而非 12px，`2xl`=20px）。
   放回 `extend`，或直接显式定义 §3 规则 9 的三档。
2. **补 `darkMode: ["selector", '[data-theme="dark"]']`。** 现在没配置 → Tailwind v3
   默认 `'media'`，将来任何人写 `dark:` 都会静默绑到操作系统而非 App 开关。
   即使禁止写 `dark:`，也要设上这道护栏。
3. **删除死键**：`boxShadow` 的 5 个键（全站 0 引用，而全站 `boxShadow` 总用量只有 2）、
   `colors` 里的 `pg-white`/`pg-black`/`pg-black-soft`/`pg-panel`/`pg-panel-2`/
   `pg-panel-3`/`pg-white-soft`/`pg-text`/`pg-muted`/`pg-muted-2`、
   legacy 六色（`canvas`/`ink`/`line`/`positive`/`warning`/`danger`，全部 0 引用）、
   以及写死的 `bg-card-hover: "#212123"`。
   **注意：先逐个替换 45 行 `bg-pg-white|text-pg-black` 引用，再删色板，最后跑 tsc。**

---

## 5. 主题引擎（一次做完 D1 / D3 / D5–D9）

### 5.1 防闪 + System 三态

扩展 `app/layout.tsx` 里已有的 `beforeInteractive` 脚本（它现在只处理
`data-visual-style`），加入主题与字号解析，**必须在首帧之前落地**：

```js
var pref = localStorage.getItem('pg_theme') || 'system';
var resolved = pref === 'system'
  ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  : pref;
document.documentElement.dataset.theme = resolved;
document.documentElement.dataset.themePreference = pref;
document.documentElement.style.colorScheme = resolved;   // 修 D9/I
```

- `appearance-controls.tsx` 的 `useEffect` 只负责读取后同步 React state，
  **不再承担"首次应用主题"**。
- **`pg_font_scale` 进同一个 pre-paint 脚本** —— 它现在也只在 effect 里应用，
  导致挂载后从 16px 重排到 14/18px。
- CSS 补 `:root { color-scheme: light }` / `:root[data-theme="dark"] { color-scheme: dark }`。
  现在全仓库 **0 处** `color-scheme`，所以原生 `<select>` 弹层、滚动条、
  `input[type=date]`（`usage-panel.tsx` 两个日期选择器）跟的是操作系统而不是 App。
- 三态 UI：**System / Light / Dark**（现在是二态开关）。
- 新增 `prefers-color-scheme` 变化监听：preference 为 system 时实时跟随。

### 5.2 修三处实例不同步（D 类）

`<AppearanceControls>` 挂在 **3 个位置**（`nav.tsx` 侧栏 / 顶栏桌面 / 顶栏移动），
各自独立 `useState`，无 storage 监听。把 theme / fontScale / visualStyle 提到一个
Context 或极简 store，并监听 `window` 的 `storage` 事件做跨标签页同步。

### 5.3 皮肤层降级（不删）

`globals.css` 409–458 行那段必须改：它把 `--panel` / `--border` 重写成 rgba，
使语义 token 失去唯一真值。改成只覆盖皮肤自己的变量：

```css
:root[data-visual-style="glass"] { --skin-surface-blur: 12px; --skin-surface-fill: …; }

.pg-surface-1 { background: var(--pg-surface-1); }
[data-visual-style="glass"] .pg-surface-1 {
  background: color-mix(in oklab, var(--pg-surface-1) 90%, transparent);
  backdrop-filter: blur(var(--skin-surface-blur));
}
```

方向（需确认，默认如此）：**不删 glass**（`visual-style.spec.ts` 依赖它），
但把它从"默认 + 重写 token"降级为"可选皮肤 + 局部覆盖"。
保留 `.shell-chrome` / `.shell-rail` / `.liquid` 三处 `backdrop-filter`（有理由），
删除其余 20 余处无差别 blur，删掉 body 上的 ambient radial-gradient 与
`.chronosphere-field` 的径向渐变。

同时修 `.liquid-surface` 只在 glass 下有样式的问题（base 规则漏了它）
→ classic 皮肤下 `chrono/liquid-surface.tsx` 现在渲染一个完全无样式的 `<section>`。

### 5.4 修 `useHtmlDataset`（D7，一处改五个调用点全好）

`lib/chrono.ts` 用 `el.getAttribute("data-" + name)`，而 5 个调用点全部传驼峰
`"visualStyle"` → 实际查找 `data-visualstyle`，元素上是 `data-visual-style`，
**恒返回 null，MutationObserver 的 attributeFilter 也盯错名字**。
在函数内做 camelCase → kebab-case 转换，并对转换后的名字做 attributeFilter。
受影响的 5 处：`chrono/liquid-surface.tsx`、`chrono/chrono-entrance.tsx`、
`chrono/chronosphere.tsx`、`chrono/chrono-slices.tsx`、`terminal/liquid-lens.tsx`。

### 5.5 Focus（D3）

把唯一的 focus 规则从 glass 门控中提出，提升为全局：

```css
:where(a, button, input, select, textarea, summary, [tabindex]):focus-visible {
  outline: 2px solid var(--pg-focus-ring); outline-offset: 2px; border-radius: inherit;
}
/* 输入类用柔和 ring，不要 2px 硬描边 */
.pg-input:focus-visible { border-color: var(--pg-border-focus); box-shadow: 0 0 0 3px var(--pg-focus-ring); outline: none; }
```

清掉 33 处裸 `outline-none` 里**没有补焦点样式**的那些。
最关键的两处是 `agent-chat.tsx` 的 textarea 与模型 `<select>`。

### 5.6 修未定义变量引用（D9）

`globals.css` 343 / 362 / 376 引用 `var(--bg-panel)`，363 / 377 引用
`var(--border-pg)`，**两个名字全仓库从未声明且无 fallback** → 整条声明失效，
一段可见的流动边框直接消失。改成正确 token。
顺带清掉 `trading-architecture.tsx` 的 `var(--text-pg, #9ca3af)`。

---

## 6. 反色按钮（D1 —— 全站最大的一处视觉语言缺陷）

实测：**45 行 / 90 处** `bg-pg-white|text-pg-black`，散布在 **30 个文件**，
而 `pg-white` / `pg-black` 在 tailwind config 里写死。Light 主题下
`--panel` 也是 `#ffffff` → 主按钮白底白边黑字，边界消失。

```css
:root {
  --pg-surface-inverse: var(--pg-text-primary);
  --pg-text-inverse:    var(--pg-bg-page);
}
:root[data-theme="dark"] {
  --pg-surface-inverse: #fafafa;   /* 暗色下主按钮反色为亮色 */
  --pg-text-inverse:    #0f1115;
}
```

建立**唯一**按钮系统，扩展现有 `components/ui.tsx` 的 `Button`：

```
variant: primary | secondary | ghost | danger
size:    sm | md | lg

primary   → bg var(--pg-surface-inverse) / text var(--pg-text-inverse)
            hover: opacity .92 · min-h 36 / 40 / 44
secondary → bg var(--pg-surface-2) / text var(--pg-text-primary)
            border 0.5px var(--pg-border-default) / hover bg var(--pg-surface-hover)
ghost     → transparent / text-secondary / hover bg var(--pg-surface-hover)
danger    → 仅危险写操作：bg var(--pg-danger-soft) / text var(--pg-danger)
```

现有 `<Button>` 有 189 处调用、raw `<button>` 176 处。目标：raw 降到 ≤80。
**不要一次性重写所有按钮** —— 先 45 行反色，再按页面推进。

同时修 D10 的第三个失败项：`.command-submit` 的 `#fff` on dark `--accent`
实测 **3.16:1**（11.5px 正文需 4.5:1）。反色按钮文字一律走 `--pg-text-inverse`，
并在 token 层保证 ≥4.5:1。

---

## 7. Markdown（D2 —— 投入产出比最高）

Chat 是产品核心，而它的回答**目前完全没有排版**：

- `puregamma.tsx` 用的 `prose prose-invert prose-headings:…` 依赖
  `@tailwindcss/typography`，而 `package.json` 里**没有**、`plugins: []`
  → 这些 class **产出 0 条 CSS**。
- `.pg-report` 被引用但**从未定义**。
- `remark-gfm` **0 引用** → 管道表格不解析，原样输出成文字。
- `ReactMarkdown` 没有 `components={{}}` → 标题继承正文字号、`ul/ol` 被 preflight
  重置成无符号无缩进、引用块与表格无样式、代码块无 header / 语言标签 / copy / 横向滚动。

**不要引入 `@tailwindcss/typography`** —— 它的默认排版会与 §3 规则 6 的字号系统冲突。
手写一份 `pg-markdown` 样式表（可放 `app/markdown.css` 并在 layout 引入），全部消费 `--pg-*`：

```
h1 24/32·500  h2 20/28·500  h3 18/26·500  h4 16/24·500
p 14/22 或 16/24（跟随 data-font-scale），段间距 16px
ul/ol 恢复 list-style + padding-inline-start: 24px + 项间距 8px
blockquote 左边 2px var(--pg-border-strong) + text-secondary
hr border-top var(--pg-hairline) solid var(--pg-border-subtle)
a var(--pg-accent)，静默无下划线，hover 加下划线
code 行内：var(--pg-surface-2) + radius-sm + mono 13/20
pre：var(--pg-surface-2)（暗色下比 page 更深）+ radius-md + hairline + overflow-x auto + padding 16px + mono 13/20
table/th/td：只有横向 hairline，表头 text-secondary 12/18·500，无竖线、无斑马
```

- `puregamma.tsx` 删掉全部 `prose*`，换 `pg-markdown`，并加 `break-words`。
- 加 `remark-gfm`。
- 代码块加**薄** header（语言 + copy）。不要 VSCode 大黑框，暗色下也不要与页面断裂的纯黑。
  参考 `api-docs-embed.tsx` 已有的 `overflow-x-auto` 与 `gateway-console.tsx`
  已有的 copy 交互，抽成共用组件。
- `components/markdown.tsx` 现在只是 7 行 re-export，聊天根本没用它 →
  把新的渲染器放进这个文件，让三处调用点走同一个组件。

---

## 8. Chat 工作区（本轮最大工程量）

### 8.1 统一宽度契约（D4）

`/chat` 走 `ChronoSlices → IntelligenceShell`（`.intelligence-shell{max-width:1180px}`），
`/chat/[conversationId]` **什么都不走**，直接渲染 `<AgentChat>`。
同一个聊天在两条路由间切换，内容列左右各变化约 100–200px。

- 把 `IntelligenceShell` 也应用到 `/chat/[conversationId]`，
  **或更好：让 `AgentChat` 自己拥有宽度契约**，不再依赖页面级包裹。
- 内容列宽度写成一个 token `--pg-chat-measure`，**且不随 `data-font-scale` 缩放**
  （现在 `max-w-3xl` = 48rem 会在 672 / 768 / 864px 之间跳）。
- composer 与内容列同宽。

### 8.2 垂直预算：composer 必须在折线以上

现状：`IntelligenceShell` 的 header（eyebrow + `clamp(2.6rem,6vw,4.2rem)` 大标题 + byline）
占掉约五分之一屏；卡片是 `h-[calc(100dvh-7rem)] min-h-[620px]`，
所以文档高度 ≈ 视口 + header 高度。**实测截图确认：1440×900 下 composer 在折线以下；
390×844 手机上完全看不到。**

把 header 收成一行，或让卡片高度基于容器而不是 `100dvh`。

### 8.3 移动端历史必须可达（D5 —— 可用性缺陷）

`agent-chat.tsx` 的侧栏是 `hidden … lg:flex`，且**没有抽屉**。
低于 1024px 时对话列表、"新会话"、"删除全部历史"全部消失，
用户只能靠 `/dashboard` 的 Today activity 链接或手输 URL 回到旧对话。

做 `lg` 以下的 Drawer，复用 `nav.tsx` 里 `MobileNavDrawer` 的既有模式
（`fixed inset-y-3 left-3 z-50 w-80 max-w-[85vw]`、
`-translate-x-full → translate-x-0`、`transition-transform duration-200`、
scrim `fixed inset-0 z-40`）。入口按钮放在 composer 上方那一行。

### 8.4 长内容防裁切（D6）

`agent-chat.tsx`（564 行）里 **0 处 `break-words`、0 处 `overflow-x-auto`**，
祖先有 `overflow-hidden` → 实测长文本/长 URL 被**静默裁掉**，无省略号无滚动条。

修：markdown 容器加 `break-words`；`pre` / `table` 加 `overflow-x-auto`；
`chat-panels.tsx` 的 3 列网格加 `min-w-0`。

⚠️ **注意**：现有 `contrast-audit.spec.ts` 的溢出断言
（`scrollWidth <= clientWidth + 1`）因为裁切而**恒为真**。修完必须换一个
真能检测溢出的断言（例如对未裁切的容器测 `scrollWidth`，或断言不存在
`overflow-hidden` 祖先下的超宽子元素）。

### 8.5 常驻 UI 从 6 行降到 2 行

现在的 composer 区恒定渲染 6 行：

| 行 | 处理 |
| --- | --- |
| 研究模式开关 + 一行解释 | 解释文字删；开关收进 composer 内部 |
| "Model for this turn" 标签 + select | 删标签，改成 composer 内一个轻量 model chip |
| 模型异常提示 | **保留** —— 只在异常时出现，符合"安静"原则 ✓ |
| 高级研究设置折叠卡（带边框） | 删外层边框，改 composer 内 ghost 按钮 + popover |
| form（attach / textarea / send） | 重做为 §8.6 |
| footer + `Estimated cost: - Credits` | 报价存在时才显示；否则整行删除 |

另外三处常驻噪音：`ocean-shell.tsx` 的浮动 "Motion / Static" 按钮压在卡片右上角
→ 收进设置；最新回答下方常驻 3 个交叉链接 → 只在用户打开 sources 时出现；
侧栏头部的 credits 行 → 降为 tertiary，不要与 "PureGamma Agent" 同级。

### 8.6 Composer 重做

```
┌─────────────────────────────────────────────┐
│  Ask PureGamma about markets, portfolios…    │   ← 无边框 textarea
│  [+]  DeepSeek V4.1 Flash ▾        [ Tools ] │   ← 底层工具行
└─────────────────────────────────────────────┘
                                            ( ↑ )
```

- **一个** raised surface 容器：`background: var(--pg-surface-raised)`、
  `border: 0`、`box-shadow: var(--pg-elevation-soft)`（0.5px stroke 首层）、`radius-lg`。
- 现在是 **5 层嵌套边框**（OceanShell 边 → 包裹层 → grid 边 → composer border-t →
  textarea 边），**降到 1 层**。textarea 自身 `border: 0; background: transparent`，
  focus 交给外层容器的 ring。
- 发送按钮从 `h-14 w-12`（48×56px 白方块）改为 32–36px 圆角图标按钮；
  disabled 用 `opacity: .35`；busy 时被 stop 替代，stop 用 `--pg-danger` 文字但**不加实色底**。
- attach 从 `h-14 w-11` 改为 32px ghost。
- 附件上限提示（5 个 / 20KB / 50KB）不要常驻，超限时才在容器内出现一行。
- **Thinking / Tools 目前没有任何 UI 控件**（`agent-chat.tsx` 里 thinking 只有文案，
  0 个 state / handler）。后端不支持就不要造假控件，本轮跳过。

### 8.7 消息渲染

| 现状 | 处理 |
| --- | --- |
| user：`ml-auto max-w-[85%] border bg-bg-panel-muted p-3`，**无圆角** | 改 `radius-lg` + `--pg-surface-2` + 无边框 + `max-w-[min(85%,42rem)]` |
| assistant：左边框 + 内距 | **保持**（已经非卡片化，方向正确）✓ |
| 每条消息都打 byline（模型名） | 收敛为整段对话**只在第一条 assistant** 标一次 |
| 流式态把 `"Analyzing..."` 当正文渲染 | 改为安静的 streaming 指示（caret 或 3 点），不要用正文字号占位 |
| 载入态 `min-h-64` 旋转图标（≥256px 空白块） | 改局部骨架，保持结构稳定 |
| 消息级操作（copy / retry） | `group-hover` + `focus-visible` 出现，常驻 0 个 |

### 8.8 Agent 状态与 tool calls

保持：`AgentStageIndicator` 是**小内联状态行**（约 2rem），带
`role="status" aria-live="polite"`。**不要改成大 loading card。**
计划 / 证据行同样是小行，保持。

必须修：

- **tool 失败与成功视觉完全一致**（同一套 `border px-2 py-1 text-xs text-text-pg-muted`，
  失败时颜色不变、图标不变、无错误文案、无时长、不可展开）→ 失败才突出：
  `--pg-danger` 文字 + `!` 图标 + 可展开详情；成功态保持安静。
- **非 strategy 类 tool 结果完全不渲染**（`chat-panels.tsx` 只在名字含
  `strategy|activation|order_preview` 时返回内容）→ market / quote / news / portfolio
  的结果被静默丢弃。至少渲染一个可展开的 "N results" 行。
- tool chip **只追加不清除** → 只保留本轮，历史折叠。

### 8.9 空状态与错误态

- 空状态 4 张 starter card → **3 张**；卡片去边框，改 `--pg-surface-2` + hover surface。
- **错误态现在渲染在 composer 区而不是 transcript 里 —— 位置反了，用户会漏掉。**
  改成 transcript 末尾的内联行：一行 `--pg-danger` 文案 + Retry + Details 折叠。
  不要 System Error 500 / traceback / JSON。
  现有 `lib/chat-errors.ts` 的文案映射与计费三态（refunded / settled / unknown）
  **质量很好，保留**。
- 全站没有 toast 系统，现在是内联 banner。**本轮不要新增 toast。**

### 8.10 无障碍

- 图标按钮现在用 `title` 而非 `aria-label`（`agent-chat.tsx` 6 处：
  侧栏折叠、新会话、删除会话、删除全部、附件、发送）→ 全部补 `aria-label`。
  （全站 `aria-label` 51 处 / `<button title=` 10 处，说明习惯已经建立，只需补齐。）
- 流式回答不在 live region 里 → 给 assistant 容器补 `aria-live="polite"`，
  但**不要逐 token 播报**（用 `aria-busy` + 完成时一次性播报）。
- 全站 `motion-safe` / `motion-reduce` 类 **0 处**，而 `prefers-reduced-motion`
  在 CSS 里有 7 处 → 补 `animate-spin` 与 `scrollTo({behavior:"smooth"})` 的
  reduced-motion 分支。

---

## 9. 把 border 换成留白（818 → ≤450）

### 9.1 通用

```
优先级：留白 > 排版 > hairline 分隔 > surface > 带边框卡片
新增 .pg-divider { border-top: var(--pg-hairline) solid var(--pg-border-subtle) }
新增 .pg-section { display:flex; flex-direction:column; gap:32px }
```

**不要试图全局替换 818 处。** 只处理每个页面/组件里"为了分组而加的壳"。

### 9.2 首页（工程量最小，优先级最低）

| 问题 | 位置 | 处理 |
| --- | --- | --- |
| Hero 区 **3 个 CTA** | `app/[locale]/page.tsx` | 降到 2：Primary `开始对话`、Secondary `API 快速接入`；`查看定价` 移页脚 |
| 卡片内又套品牌行（顶栏已有 logo） | `page.tsx` 品牌行 | 删除 |
| 同一个模型公告渲染 3 次 | hero banner / model section / footer rotator（4500ms 自动轮播） | 只留 model section 那一次；**删掉自动轮播**（无用户价值的自动动画） |
| 公告文案与真实状态不一致 | hero banner 的 tone 跟随目录，但文案写死 "is now available" | 文案必须跟随 `availability.state`，否则删掉这个 badge |
| 首屏 23 个带边框容器，其中 17 个是架构图节点 | `trading-architecture.tsx` | 节点去边框，改 surface + 连接线；`h-[520px]` 固定高在移动端是灾难 |

目标：首屏 CTA **2** 个、带边框容器 **≤8** 个、常驻 badge **≤2** 个。

### 9.3 Model Section（保持上一轮 227px 的轻量结构，只换皮）

结构正确，**不要加内容**。只改视觉：

- 1px `border-border-pg` → hairline `--pg-border-subtle`
- `bg-bg-panel` → `--pg-surface-1`；`rounded-2xl`(20px) → `--pg-radius-lg`(12px)
- `Available` 徽章改安静：现在是药丸 + Check 图标 → 改 **● Available**
  （6px 圆点 + secondary 文字），**只在异常态才用颜色强调**。
  复用已有的 `StatusDot`。
- 3 个 CTA → **1 主 CTA + 1 行 tertiary 文字链接**
- `data-model-availability` 属性被 e2e 断言，**保留不动**

### 9.4 Admin（约 10%）

事实：`/admin` 稳态渲染 **13 个带边框 tile**、`space-y-5`（20px 节奏），
是全站最密的面；而 `/dashboard` 用 `.terminal-panel` + 32–72px 的 `--section-gap`，
是最舒展的。**两者必须统一。**

| 问题 | 位置 | 处理 |
| --- | --- | --- |
| Admin nav 是横向 chip 行，不是侧栏；且 `active = activePath === item.href` 是**精确匹配** → `/admin/gateway` 永远点不亮 `/admin` | `admin/layout.tsx` | 改纵向分组侧栏；改**前缀匹配** |
| `/admin` 在全局导航里不存在，唯二入口是 internal login 的 redirect 与页内一张卡 | `nav.tsx` | 给 admin 角色加一项 |
| 13 个 tile（`admin/page.tsx` 5 + `admin-credit-console.tsx` 8） | — | 降到 ≤7：4 个指标改**裸排版**（数字大、标签小、无框、靠留白分组），不要 4 个 MetricCard |
| 异常不突出：`tone` 只作用到 6px 的 StatusDot，数字在 0 与 10000 之间长得一样 | `admin/page.tsx` | 有异常时**数字本身**用 `--pg-warning` / `--pg-danger` + 一行说明 |
| 每个指标卡都带同尺寸 muted detail | `puregamma.tsx` | 删除，或降为 caption 且仅有值时才显示 |
| 8/11 个 i18n `module` key 是孤儿 | `messages/*/admin.json` | 接线或删除。**不要留"承诺了但不存在的面"** |
| Admin 表格三套实现（`pg-table.tsx` / bespoke `admin-users-table.tsx` / `data-source-table.tsx` 其实是卡片网格） | — | 统一到 `pg-table.tsx`：横向 hairline only、表头 text-secondary 12/18、行 hover `--pg-surface-hover`、**无竖线、无斑马**；三处都要有 hover |
| 分页半接线：`stripe-events` 解析 `?page=` 但不渲染分页控件；`billing-intents` 既无筛选也无分页 | — | **补齐或隐藏。不要显示一个用户到达不了的数字。** 后端 `apps/api/services/pagination.py` 已提供 `total/limit/offset/page/has_more`，直接用 |

**已做对、保持**：Admin nav 的 active 是 subtle surface（不是大蓝块）✓；
`admin-users-table.tsx` 的服务端分页契约（250ms debounce + `requestRef` stale guard）
质量很好 ✓ 被 spec 锁定，**不要改行为**。

### 9.5 Account / Billing / Dashboard

- `account/page.tsx`：**8 个 ResearchCard、0 个裸 section** → 改 3 个 section
  （Identity / Agent / Security），组内用 hairline + 留白。
  其中一段约 4KB 的单行 JSX（iMessage 表单）拆成子组件。
  ⚠️ 该文件**同时在 X Login 的 WIP 列表里** —— 动之前先对齐，或本轮跳过。
- `billing/page.tsx`：6 个 ResearchCard + 6 个 badge + 4 个 plan 卡片 →
  plan 卡片降为一行对比条目，不要 4 个等重卡片。
- `dashboard/page.tsx`：7 个 `.terminal-panel` 用 32–72px 间距，与 admin 的 20px 冲突
  → 统一到两档（紧凑 24 / 舒展 40）。

### 9.6 死代码清理（一次性）

| 类别 | 清单 |
| --- | --- |
| JSX 在用但 CSS 不存在 | `.hub-hero`、`.chrono-slice`、`.chrono-decision-stream`、`.portfolio-nav`、`.chronosphere-motion`、`.pg-report` |
| 定义但 0 引用 | `components/ui.tsx` 的 `Card`；`components/how-it-connects.tsx`（179 行）；`lib/theme.ts` + `components/theme/tokens.ts`（互相引用，全站零导入） |
| 未定义变量 | `globals.css` 的 `--bg-panel` / `--border-pg`；`trading-architecture.tsx` 的 `--text-pg` |
| Tailwind 死键 | `boxShadow` 5 键；colors 的 10 个 `pg-*` + legacy 6 色；`bg-card-hover` |
| 死 radius 档 | `rounded-sm`（0 引用）、`rounded-3xl`（0 引用）、裸 `rounded`（0 引用） |
| 重复 Badge | `ui.tsx` 的 `Badge`（**0 文件导入**）+ `puregamma.tsx` 的 `Badge`（24 文件）+ `ocean/status-badge.tsx`（第三套：StatusBadge / StatusBadgeWithPulse / CapabilityBadge / LoadingBadge）→ 合并为一套。**注意 `ui.tsx` 的 `Badge` 不是"有人在用"，是纯死代码** |
| 卡片原语四份 | `ui.tsx` Card（死）、`puregamma.tsx` ResearchCard/PGResearchCard、`.terminal-panel`、`.liquid/.lens-surface` → 收敛为一个 `pg-surface` + 2 变体（flat / raised） |
| 缺失的交互原语 | Modal / Dropdown / Tooltip / Popover / Tabs 全部不存在：5 处手写 modal，`createPortal` **0 处**、无 focus trap、无 Escape、无滚动锁 → 至少抽出 Modal/Drawer + Popover 各一个 |

---

## 10. 截图与验证

### 10.1 截图（产出到 `.preview-round5/`）

必要成对（同 viewport、同 stub、同滚动位置）：

```
home-light / home-dark
chat-empty-light / chat-empty-dark
chat-streaming-light / chat-streaming-dark        ← 新增：验证流式 + tool 状态
admin-light / admin-dark
gateway-light / gateway-dark
billing-light / billing-dark
mobile-home-light / mobile-home-dark              (390×844)
mobile-chat-light / mobile-chat-dark
mobile-chat-drawer-light / mobile-chat-drawer-dark  ← 新增：验证 §8.3
```

**已有的 before 基线在 `.preview-round5-before/`**（16 张，1440×900 与 390×844），
可直接做对照。复用 `apps/web/capture-v41-flash-screenshots.mjs` 的脚本骨架。

⚠️ Chat 与 Admin 需要会话桩。`contrast-audit.spec.ts` 里有可复用的 stub 模式，
但它有一个坑：**Playwright 的路由是后注册优先**，所以宽泛的
`**/me`、`**/admin/**` fallback 必须**先**注册，具体桩后注册；
顺序写反会让具体桩被静默遮蔽。这个坑在 `admin-console.spec.ts` 里已记录。

### 10.2 浏览器真实检查（不能只看截图）

用 Playwright `evaluate` 读关键节点的 computed style，确认真的在用 token：

```
backgroundColor / color / borderColor / borderWidth / boxShadow / fontSize / fontWeight / borderRadius
```

至少覆盖：`body`、`.shell-rail`、`.shell-chrome`、一行 `pg-table` 行、composer 容器、
textarea、assistant 消息、`pre` 代码块、一个 dropdown / menu、一个 modal。

### 10.3 新增测试

| 文件 | 断言重点 |
| --- | --- |
| `theme-system.spec.ts` | light / dark / system 三态；刷新后保持；**刷新瞬间 `documentElement.dataset.theme` 已是最终值**（防闪回归）；`colorScheme` 已设置；`data-font-scale` 同样无闪 |
| `theme-popover.spec.ts` | 暗色下打开 menu / select / dialog / tooltip 不出现白色；亮色下不出现深色 |
| `chat-design.spec.ts` | `/chat` 与 `/chat/[id]` 内容列宽度**完全相等**；composer 在 900px 高视口内可见；长 URL / 长 hash **不被裁切**（这条现在恒为真，因为裁切掩盖了溢出）；assistant 不是卡片；tool 失败与成功视觉不同 |
| `markdown-render.spec.ts` | 构造含 h1–h3 / ul / ol / blockquote / table / 行内 code / 代码块的回答，断言每类元素的 computed `fontSize` / `listStyleType` / `borderTopWidth` **≠ 默认值**（防"prose 没插件"回归） |
| `admin-theme.spec.ts` | admin 在 light/dark 都无白底断裂；active nav **前缀匹配**生效 |
| `mobile-theme.spec.ts` | 390×844 / 430×932 无横向溢出；**chat 历史抽屉可打开并能进入旧对话** |
| `hairline-audit.spec.ts` | 中性分隔线 computed `borderTopWidth ∈ {0, 0.5, 1}`；不存在 border 与 elevation shadow 同时非 0 的浮层 |

### 10.4 扩展现有 `contrast-audit.spec.ts`

它现在**只 console.log 不断言**（唯一断言是 overflow，而那条因为 §8.4 的裁切恒为真）。

1. 加 `expect(failures).toHaveLength(0)`。
2. 覆盖从 `/zh/chat` 扩到 home / chat / admin / gateway / billing / account × light / dark。
3. 额外覆盖 placeholder / caption / `--pg-text-tertiary` / field label / disabled。
4. 它的合成算法（把 fg 合成到最近**不透明**背景）是正确的 —— 引入 glass 透明度后
   必须保留这个逻辑，否则会误报。

### 10.5 检查清单（每个 viewport × 每个页面）

Viewport：**390×844、430×932、1280×800、1440×900、1920×1080**
页面：Home、Chat（空 / 有对话 / 流式中）、Admin、Gateway、Billing、Notifications、Data Sources

每次必查：主题断裂（暗色下白卡 / 亮色下黑 modal）· 刷新白闪 · 横向溢出（含长 URL / 宽表格）·
文本对比度 · focus-visible 可见（含 classic 皮肤）· `prefers-reduced-motion` 下无动画 · CLS

---

## 11. 本轮不修改业务

原则不动：Auth、Billing/Stripe 逻辑、Credits 逻辑、Gateway 路由、Pricing、
Agent backend、数据管线、交易、组合计算。

**例外（本轮要动，因为它们是 UI 缺陷）**：
- `messages/*/landing.json`、`model-upgrade.json`、`admin.json` 的文案删除/缩短；
- 首页 CTA 数量；
- Admin 分页控件补齐或隐藏（**只改前端渲染，不改后端契约**）。

若发现后端 bug：单独记录到 `docs/frontend/BACKEND_BUGS_ROUND5.md`，**不要顺手重构**。

---

## 12. 执行顺序（按依赖，不要并行乱改）

```
Phase 0  审计 —— 已完成，读 docs/frontend/ 三份文档即可，不要重做
Phase 1  Token 层重排 + 别名 + tailwind.config 三处修复
         验收：tsc 通过、页面视觉不变（别名指向同样的值）—— 零视觉差异重构
Phase 2  主题引擎（防闪含 font-scale + System 三态 + color-scheme
                   + 全局 focus-visible + 皮肤层降级 + D7/D8/D9）
         验收：theme-system.spec + 手动刷新无闪
Phase 3  反色按钮 45 行替换 + 按钮系统统一 + 删死色板 + D10 对比度   ← 第一个用户可见变化
Phase 4  Markdown（手写样式表 + remark-gfm + 代码块 header）
Phase 5  Chat 工作区（宽度统一 → composer → 移动端抽屉 → 消息态 → tool 失败态 → 溢出保护）
Phase 6  Admin（侧栏 + 前缀匹配 + 密度 + 表格统一 + 分页）
Phase 7  首页与其余页面密度 + 死代码清理
Phase 8  截图 + 对比度全量 + 交付报告
```

每个 Phase 单独提交，commit message 沿用仓库现有 `feat(web):` / `fix(web):` /
`refactor(web):` 风格。

---

## 13. 施工前的 Git 保护（第一步就做）

```bash
git status                 # 17 modified + 大量 untracked
git branch --show-current  # main
git rev-parse HEAD         # cf8535ee3234f2ebab25f2e96b23c55d6c7a57c2
git log --oneline -20
```

**必须保护的未提交 WIP**（X Login 相关，另一位工程师在做）：

```
M apps/api/routers/auth.py, email_auth.py, imessage_agent.py, main.py, config.py
M apps/web/app/[locale]/(auth)/login/page.tsx, signup/page.tsx
M apps/web/app/[locale]/account/page.tsx          ← 同时是本轮 §9.5 的目标文件
M apps/web/messages/en/common.json, zh/common.json
M packages/database/models.py, session.py
M packages/notifications/dispatcher.py
M packages/workers/scheduler.py, tasks.py
M tests/security/test_production_configuration.py
M scripts/validate-production-env.py
M deploy/production.env.example
?? apps/api/routers/x_auth.py, x_bot.py
?? apps/api/services/x_bot_service.py, x_inbound_service.py, inbound_agent_service.py
?? apps/web/app/[locale]/auth/x/
?? apps/web/components/x-logo.tsx
?? packages/notifications/x_provider.py
?? docs/X_AUTH_AND_BOT.md
?? scripts/x_bot_preflight.py
```

**明令禁止**：`git add .`、`git reset --hard`、`git checkout -- .`、强推、
任何会把上述文件回滚的操作。

**推荐**：开工前 `git switch -c ui/round5-design-system`，让 X Login 的 WIP
留在工作区不动。提交时只 `git add` 本轮涉及的文件。

⚠️ `account/page.tsx` 同时出现在 WIP 与本轮清单里 → **动它之前先与做 X Login 的人对齐，
或本轮先跳过**，等 X Login 落地再回来。

---

## 14. Definition of Done

全部达成才算完成。

**DESIGN SYSTEM**
- [ ] `globals.css` 按 §4.1 的 5 层重排，**Light 为 `:root` 默认**，Dark 全表覆盖
- [ ] 语义 token 表建立，旧名保留为别名（零视觉差异）
- [ ] 三档圆角 + 三档边框 + 三档阴影，无新增 16/18/20/24px 圆角
- [ ] 中性边框统一 hairline；浮层不带 border
- [ ] 按钮系统统一（4 variant × 3 size），raw `<button>` 176 → ≤80
- [ ] Tailwind 死色板 + 死 shadow 键已删；`borderRadius` 放回 `extend`；`darkMode` 已设 selector
- [ ] `npx tsc --noEmit` 通过

**10 个缺陷**
- [ ] D1 反色按钮 90 处 → 0
- [ ] D2 Markdown 有样式（prose 0 条 CSS → `pg-markdown` 覆盖 6 类元素）
- [ ] D3 focus-visible 全局生效（含 classic）
- [ ] D4 `/chat` 与 `/chat/[id]` 内容列宽度相等
- [ ] D5 移动端可访问对话历史
- [ ] D6 长内容不被静默裁切
- [ ] D7 `useHtmlDataset` 修正，5 个调用点正确响应
- [ ] D8 `--ocean-*` 补 light 变体
- [ ] D9 未定义变量引用清零
- [ ] D10 三处临界/失败对比度全部 ≥4.5:1

**THEME**
- [ ] Light / Dark 各自独立设计（不是反色）
- [ ] System / Light / Dark 三态
- [ ] 刷新无闪（pre-paint 同时覆盖 `data-theme` 与 `data-font-scale`）
- [ ] 主题持久化；`color-scheme` 已设置
- [ ] glass 不再重写语义 token
- [ ] 所有 popover / modal / dropdown / select / tooltip 两主题正确
- [ ] 3 处 AppearanceControls 同步 + 跨标签页同步

**CHAT**
- [ ] composer 折线以上可见（1440×900 与 390×844）
- [ ] composer 从 5 层边框降到 1 层，常驻行 6 → 2
- [ ] assistant 非卡片化（保持）+ 模型名不再每条重复
- [ ] streaming 不再把 "Analyzing..." 当正文
- [ ] tool 失败与成功视觉不同；非 strategy tool 结果不再丢弃
- [ ] 错误态在 transcript 内
- [ ] 空状态 ≤3 张 starter card

**ADMIN**
- [ ] 与主站共享设计系统（同一 surface / 同一间距节奏）
- [ ] 侧栏 + 前缀匹配 active；`/admin` 从全局导航可达
- [ ] 带边框 tile 13 → ≤7；异常时数字本身变色
- [ ] 表格统一到 `pg-table`，横向 hairline + 行 hover
- [ ] 分页控件与真实可达数据一致

**HOME**
- [ ] 首屏 CTA ≤2；模型公告只出现 1 次且文案跟随真实状态
- [ ] Model section 保持 227px 级轻量 + hairline + 安静 Available
- [ ] 架构图节点去边框；带边框容器 ≤8

**ACCESSIBILITY**
- [ ] WCAG AA：正文 ≥4.5:1、大字 ≥3:1，`contrast-audit.spec` **有断言且失败数 = 0**
- [ ] placeholder / caption / label / disabled 全部达标；`--muted-2` 不再用于 11px 以下
- [ ] 图标按钮用 `aria-label`
- [ ] 流式回答进 live region 但不逐 token 播报
- [ ] `prefers-reduced-motion` 全覆盖

**RESPONSIVE** — 390 / 430 / 1280 / 1440 / 1920 全部无横向溢出

**BUILD** — tsc exit 0 · lint 干净 · `next build` 成功 · Playwright 全绿（含 7 个新 spec）·
截图产出 · 死代码清理完成

---

## 15. 最终交付报告（不允许写"优化了一些 UI"）

1. **Before / After** —— ≥5 组同 viewport 对照（home / chat / chat-empty / admin /
   mobile-chat），light + dark 各一份。基线在 `.preview-round5-before/`。
2. **Design Tokens** —— Light 与 Dark 的完整语义 token 表（**实际值**，不是"见代码"），
   标注哪些新增、哪些重命名、哪些是别名。
3. **10 个缺陷的修复证据** —— 每个给 before / after 的**可验证数字**：
   ```
   D1  before = 45 行 / 90 处 / 30 文件   after = 0 处
   D2  before = prose* 产出 0 条 CSS      after = pg-markdown N 条规则，spec 覆盖 6 类元素
   D3  before = focus 规则 1 条且仅 glass  after = 全局 1 条 + 表单 ring，classic 已覆盖
   D4  before = 两条路由内容列差 ~100–200px after = 两侧相等（给实测 px）
   D5  before = <1024px 历史不可达         after = 抽屉可开可进入旧对话（spec 断言）
   D6  before = 长文本静默裁切无滚动条      after = 可滚动 + 新断言能检测溢出
   D7  before = 属性名恒 null，5 处误判     after = 5 处正确响应
   D8  before = 11 个 --ocean-* 无 light    after = 已补
   D9  before = 5 处未定义变量引用          after = 0
   D10 before = 3.16:1 / 4.50:1 / 4.52:1   after = 全部 ≥4.5:1
   ```
4. **Component Migration** —— Button / Input / Card / Table / Modal / Popover / Badge /
   Chat / Admin 各自的：旧位置 → 新位置 → 调用点数量（before → after）。
   重点报三个收敛数字：raw `<button>` 176 → ?、手写输入框字符串 28 → ?、Badge 三套 → 1 套。
5. **密度指标** —— 逐页面 before → after 表格：带边框容器数、常驻 badge 数、主 CTA 数、
   常驻 UI 元素数、`border-*` 工具类 818 → ?。
6. **截图路径** —— 全部列出。
7. **Contrast** —— 实际失败数。目标 0；非 0 则逐条列出元素 / 比值 / 要求值 / 前景背景色。
8. **Responsive** —— 每个 viewport × 每个页面的结果。
9. **Build / Test** —— tsc、eslint warnings/errors、build 时长与体积变化、
   Playwright passed / failed / skipped。
10. **Unfinished** —— 明确列出没做完的、为什么、建议下一轮做什么。**不要隐藏。**
11. **Backend bugs found** —— 单独文件，不在本轮修。

---

## 16. 最终目标

PureGamma.ai 不应该"看起来像 DeepSeek"。用户应该产生相似的**感觉**：

> 打开页面时：安静。
> 开始使用时：直接。
> 复杂功能出现时：有层次。
> 没有操作时：没有任何东西抢注意力。
> 深色和浅色：不是换颜色，而是同一套设计系统的两个完整表达。

PureGamma 的差异来自 **Financial Data / Portfolio / Agent / Research / API Gateway**，
不来自 更多 Card / 更多 Badge / 更多颜色 / 更多说明文字。

**禁止的视觉套路**：大面积 gradient、无差别毛玻璃、neon、glow、超大圆角卡片、
彩虹 icon、emoji、满屏 status badge、所有模块 card 化、纯黑暗色、纯白亮色、
大阴影、蓝色 everywhere。

**判断标准**：

> 像一个真正成熟的 AI Investment Workspace，
> 而不是一个套了金融皮肤的 SaaS Dashboard。

---

## 附：为什么顺序不能颠倒

审计结论：**这个仓库并不缺 token**（146 条声明 / 74 个名字、967 处 text token 引用、
`dark:` 仅 1 处）。它缺的是**唯一真值和收敛的刻度**：

- 五套 token 体系里，**glass 那一层重写了语义 token**，使 `--panel` 不再是真值；
- 十档圆角、6 套阴影配方、176 处重复按钮字符串、三套 Badge 词汇、四套卡片原语；
- 主题开关在 hydration 之后才生效，所以"看起来是主题问题"的现象
  （闪屏、三处控件不同步、原生控件不跟随）本质是**架构问题**。

所以顺序是：**先建立唯一真值 → 再收敛刻度 → 最后才动视觉。**
反过来先调颜色，你会在 5 个体系之间来回打架。

DeepSeek 的经历里最值得学的不是它的色值，而是两条规则：
**① 明暗只在 token 表里发生，功能组件零主题选择器；**
**② 浮层边界由 0.5px hairline stroke 作为阴影首层提供，永不与 border 叠加。**

PureGamma 在规则 ① 上已经做得很好（`dark:` 只有 1 处），
差的是把 token 表本身收敛成唯一真值；规则 ② 则完全没有采用。
把这两条落地，PureGamma 不需要"像 DeepSeek"—— 它会自己长成一个成熟的产品。
