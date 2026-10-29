# Harness 资源视图、可复现安装、退役证据与 Round 5 视觉（W4，2026-10-29）

状态：代码与测试已完成，**未做任何生产部署、生产数据库迁移、切流或实盘开启**。新能力默认关闭。
分支：`upgrade/harness-repro-visual`（从 `origin/main@913ba27` 切出，交付前合并 `origin/main`）。

本轮四项任务，按提交顺序：

| # | 主题 | 提交 |
| --- | --- | --- |
| 1 | 研究/回测资源视图（右侧栏，默认关） | `753a23e`、`358f0ad` |
| — | 顺带修复：5 个 legacy provider 漏了 `/api` 前缀 | `5f5569c` |
| 2 | 提交 `harness/pnpm-lock.yaml`，CI 冻结安装 | `26826a5` |
| 3 | Market Data / Portfolio 退役对等证据 | `0947b96`（修复）、`1563c5d`（测试与证据） |
| 4 | 手机历史抽屉焦点缺陷 + 生产构建 CI | `430120e` |
| 4 | Round 5：token 与统一 Button、字号、按钮收敛、边框收敛 | `622c9d4`、`332f93a`、`2009149`、`5915872`、`27dc922` |
| 4 | 顺带修复：仪表盘 NAV 缺失时显示 $0.00 | `cbd5293` |
| — | 合并 `origin/main`（W3 移动端契约） | `6aaccc9` |

---

## 1. 研究/回测资源视图

### 1.1 设计

上游 0.1.7-rc.1 没有 `resource.*` slot。实际可用的机制有两个：`@deepseek-ai/dsh-client-resources`（`ctx.resources.register` + `useResource`）和 `@deepseek-ai/dsh-client-ui-sidebar-right`（`ctx.sidebarRightTabs.register` + keyed slot `sidebar.right.pane.tab`）。本轮按这两个机制实现，没有自造 slot。

```text
浏览器                                   Host（持有 bearer）                 FastAPI
@puregamma/dsh-ui-research-resources
  ctx.resources: 5 个协议   ──Remote──▶ puregammaClient 网关（只读 6 个方法）
  右侧栏: 3 个资源 tab + 1 个索引页        ├─ ctx.pgResearchRuns ─▶ /api/research/runs*（含 SSE）
                                          └─ ctx.pgBacktest     ─▶ /backtest-lab/runs*
```

- **服务契约**：`@puregamma/dsh-research` 新增 `ResearchRunsService`（`ctx.pgResearchRuns`），只读：`listRuns/run/artifacts/evidence/events`。创建、取消、重试会动 credits，不在契约内。
- **Provider**：`research-legacy-api/src/runs.ts` 读 `/api/research/runs*`，自带 SSE 解析器（CRLF、注释、跨 chunk、坏帧跳过）。它由研究 provider 以子 fiber 挂载，共用同一个 per-user bearer source（`authTokenFile`），没有新增共享 token。
- **网关**（`packages/client-gateway`）：新增 `researchRuns`、`researchRun`、`researchRunWait`、`researchArtifacts`、`backtestRuns`、`backtestArtifact`。
  - 投影只取具名字段：不转发存储路径（`relative_path`）、下载 URL、未知键，也不转发 provider 的错误正文；失败原因只按 HTTP 状态分类。
  - 缺失值保持 `undefined`，不变成 0。
  - 证据链接只放行 http(s)，且不能带用户名或密码。
- **实时状态**：`researchRunWait(runId, knownStatus)` 在 Host 端跟 SSE，状态变化或 20 s 后返回一次权威读取；SSE 失败时退化成普通读取。浏览器端 `followResearchRun` 的行为：
  - 首次读取和每次失败后都先做一次普通读取（恢复）；
  - 中间靠长轮询推进，未变化时最短间隔 3 s；
  - 读取失败时保留上一次的值，标记 `stale` / `reconnecting` 并写明原因，然后指数退避（最长 30 s）；
  - 任务进入终态后停止跟踪。
- **UI 状态**：加载、失败（无值，显示失败原因）、不可用（provider 给出的原因）、过期（上一次成功读取，带过期起始时间和原因）、实时、终态，互不混用。未报告的计数显示“未报告”，不显示 0。报告 markdown 以纯文本 `<pre>` 渲染，不解析成 HTML。回测视图标注“基于历史数据的模拟”。
- **入口**：右侧栏指南页“研究与回测”列出最近的研究任务和回测任务，点击后用 `openResource` 打开对应 tab。

### 1.2 开关（默认值）

| 开关 | 默认 | 说明 |
| --- | --- | --- |
| profile 行 `puregamma-ui-research-resources` | **disabled: true** | `harness/profile/cordis.patch.yml` |
| `harness/profile/resource-views.patch.yml` | 不加载 | 只翻转上面这一行：`dsh puregamma --patch resource-views.patch.yml` |
| 网关 6 个只读方法 | 随 `client-remotes` 挂载 | 只返回当前用户 bearer 能读到的数据；UI 插件关闭时没有调用方 |

### 1.3 威胁模型

| 威胁 | 处理 |
| --- | --- |
| 凭证进入浏览器 | 浏览器侧没有 `fetch`/XHR/WebSocket/EventSource，也没有 token（源码守卫测试）；所有读取经 Remote 到 Host，bearer 只在 Host 端读取 `authTokenFile` |
| 越权读取他人任务 | FastAPI 按 `user_id` 做所有权检查（404）；Host 用的是该用户自己的 token |
| 服务器路径或内部信息泄露 | 只投影具名字段；`relative_path` 和错误正文不进视图；有变异测试 |
| XSS（报告 markdown、证据链接） | 报告按纯文本渲染；链接只允许 http(s) 且不能带凭据，并加 `rel="noopener noreferrer"` |
| 写操作被滥用 | 契约和网关没有 create/cancel/retry/export；`release-boundary-check` 白名单逐项列出 |
| 公开 profile 能力扩大 | 插件 `dsh.client.inject` 只依赖 remotes、resources、sidebar-right、locale、renderer；overlay 启用后 shell、fs、terminal、workspace-files、plugin manager、上传仍是 disabled（`public-profile-check` 与真实 `--dump-config` 都已验证） |

### 1.4 证据

- `research-resources-check`：16 例，并入 `pnpm run check`。覆盖投影、失败原因、长轮询、断线变 stale 后恢复、首次失败、不可用、地址解析、各 UI 状态、HTTP + SSE provider（per-user token 文件），以及“浏览器端无传输、无凭证”。
- 变异测试：7 处守卫各自去掉后测试都失败。这 7 处是：未报告值显示为 0、断线不标 stale、失败后不做恢复读取、转发 `relative_path`、放行任意 URL scheme、转发 provider 原文、证据读取失败显示为“无证据”。
- `public-profile-check`：新增 1 例（默认关闭；overlay 只翻转该行；与多租户 overlay 叠加后，禁用项仍是禁用）。
- 真实 DSH `@deepseek-ai/dsh@0.1.7-rc.1 --dump-config`（同 tag 的 npm 包，本机临时 `DSH_HOME`）：
  - 默认：`puregamma-ui-research-resources` 为 `disabled: true`，`ui-sidebar-right` 已挂载；
  - 加 `--patch resource-views.patch.yml`：两次 dump 的差异只有这一行（`disabled: false`）；
  - `file-upload`、`terminal-controller`、`workspace-files`、`ui-plugin-manager` 仍是 disabled。
- 未做：没有启动真实 Host 并在浏览器里打开这个 tab（需要 FastAPI、真实账号和 DSH Host 一起运行，本机内存不够同时跑）。浏览器端的验证靠 SSR 渲染测试和 bundle 检查（CI 的 “Verify Harness client bundle contract” 步骤已加入 `ui-research-resources`）。

### 1.5 顺带修复：legacy provider 漏 `/api` 前缀

FastAPI 以 `prefix="/api"` 挂载 research、research_runner、memory、secretary、skills 五个 router，但对应的 Harness provider 请求的是 `/research/...`、`/memory/...` 等路径（直连 `PUREGAMMA_LEGACY_API_URL`，中间没有反代）。真实 FastAPI 下这些调用**全部 404**，provider 看起来就是“不可用”。

新增 `tests/harness/test_legacy_provider_routes.py`：把 `harness/plugins/*-legacy-api/src` 里每个路径模板（含 `${cond ? 'a' : 'b'}` 展开）对到真实路由表。修复前 34 个路径失败，修复后 116/116 通过。

---

## 2. lockfile 与冻结安装

### 2.1 评估

| 问题 | 结论 |
| --- | --- |
| pnpm 11.7.0 的 lockfile | `lockfileVersion: '9.0'`。在空 `node_modules` 下生成，再从零跑 `--frozen-lockfile` 得到的 lockfile 与第一次逐字节相同 |
| peer 变体 | 当前只有一个 `@deepseek-ai/cordis@4.0.4(cordis-plugin-include@1.0.10)(cordis-plugin-loader@1.0.6)` 快照，所有消费者都链接到它；`.pnpm` 下只有一份 cordis |
| CI 中 vendor 与 harness 两次安装 | 两个 workspace 互不链接（harness 的 manifest 不引用 `vendor/`），各有各的 lockfile；vendor 一直是 frozen，本轮只改 harness |
| `faaf910` 忽略 lockfile 的原因 | 提交说明里没有写。推测是当时本地 lockfile 与 CI 不一致时图省事；这正是 TS2339 的来源 |
| 其他 | `@deepseek-ai/schemastery` 有 3.18.4 和 3.18.5 两个版本：3.18.5 只被 Cordis 自己的 plugin-loader 用，PureGamma 插件都解析到固定的 3.18.4。记录在案，不强制 |

结论：**可行，已实施。**

### 2.2 实施

- 从 `.gitignore` 删除 `harness/pnpm-lock.yaml`，提交用 11.7.0 生成的 lockfile（6715 行）。
- `harness-v2.yml`：`pnpm install --frozen-lockfile`。GitHub 运行 `40878982951` 通过。
- `lockfile-check`（`pnpm run check` 的第二步）：
  - lockfileVersion 为 9.0，`packageManager` 为 `pnpm@11.7.0`；
  - cordis 只有一个版本、一个 peer 变体，且所有消费者都链接到它；
  - 所有 `@deepseek-ai/dsh-*` 都是固定版本；
  - importers 与 workspace 目录一致；
  - 已安装的树里只有一份 cordis（专门抓本地过期 `node_modules`）。
- 变异测试：注入第二个 cordis 快照，或把一个 dsh 包改成 0.1.6，check 都会失败。

### 2.3 升级 DSH 时如何更新 lockfile

在 `harness/` 目录内操作（这样 corepack 才会选中 11.7.0）：

```bash
# 1. 同时改 vendor gitlink、harness/package.json 的 devDependencies 和各插件 peer（见 harness/README.md）
find . -name node_modules -type d -prune -exec rm -rf {} +
pnpm install                       # 重写 pnpm-lock.yaml
pnpm run lockfile-check && pnpm run check
git add pnpm-lock.yaml
```

`lockfile-check` 读取 `devDependencies['@deepseek-ai/dsh-web-app']` 作为 DSH 固定版本，所以升级后不需要改测试本身。

---

## 3. Market Data 与 Portfolio 退役对等证据

### 3.1 测试设计

- **金样（Python）**：`tests/harness/test_market_portfolio_parity.py` 用固定场景调用真实 FastAPI 的 `GET /portfolio` 和 `GET /market/snapshot`，结果须与 `harness/scripts/fixtures/legacy-parity.json` 完全一致。场景用冻结时钟、显式 id 和 `TZ=UTC`，SQLite 下才能确定。FastAPI 有意改动后，用 `PG_UPDATE_PARITY_FIXTURES=1` 重新生成。
- **Harness 回放（Node，进 `pnpm run check`）**：`market-portfolio-parity.test.mjs` 把同一份金样经 HTTP 喂给真实的兼容 provider（挂在真实 Cordis Context 里）和真实的模型工具（execute、render、presentationMeta），逐项比对字段、新鲜度和不可用语义。
- **实时对照**：已安装 harness workspace 时，同一个 pytest 会在回环端口起 uvicorn，Node 端用 per-user token 文件通过 HTTP 读取，然后逐字段比较。
- **单元测试**：`market-portfolio.test.mjs` 覆盖服务契约的注册与卸载、资产类别映射、残缺行、小数精度、多账户同 venue 的持仓归属、工具渲染。

场景：
- 已连接：新鲜的 Hyperliquid 账户 + 过期的 Plaid 账户，含多空持仓；
- 部分：一个账户从未同步；
- 无账户；
- 按账户过滤；
- 行情：实时、非实时、mock 模式；
- 失败：500、401、未登录。

### 3.2 对等测试发现并修复的缺陷（`0947b96`）

1. **`portfolio_snapshot`、`portfolio_nav` 对所有用户都返回“不可用”**。工具用 `accountIds: []` 表示“全部”，provider 却把它当成空过滤集，过滤掉了所有账户。
2. **从未同步的账户显示现金 0**。legacy 对它返回 `nav/available_cash = 0.0, as_of = null`；现在视为“未知”，NAV 注明“不含 N 个尚无快照的账户”。
3. **按账户过滤的 NAV 返回的是全部账户的总额**；现在是所选账户各自数值之和，as-of 用所选账户的。
4. **一个账户过期，所有账户都被标为过期**；现在按账户的有效状态（legacy 的 `STALE`）判断。
5. **SQLite 返回的无时区时间按 Host 本地时区解析**；现在一律按 UTC。
6. **`MARKET_DATA_MODE=mock` 的编造价格会作为报价交给模型**；现在丢弃 `is_mock` 报价。

变异测试：上述 6 条修复加上“NAV 缺失时工具填 0”这一条，共 7 处，逐一去掉后测试都失败（时区一项在 `TZ=Asia/Shanghai` 下验证）。

### 3.3 退役门槛对照（`retirement-evidence.json` 的 `candidates`）

`retired` 仍为空。部署镜像 digest、HTTPS 的 E2E 产物和人工审阅三项不能在本机编造，所以没有任何 surface 写进 `retired`。新增的 `candidates` 结构只记录进度，不授权删除：候选对应的 legacy 文件必须仍然存在，同一个 surface 也不能既是候选又是已退役。规则在 `scripts/retirement-gate.mjs`，测试在 `retirement-check.test.mjs`（5 例）。

| 门槛（HARNESS_CORE_V2 + 证书） | market.py | news.py | portfolio.py | 缺什么 / 谁来补 |
| --- | --- | --- | --- | --- |
| Service Definition 版本化且有测试 | 部分 | 部分 | 部分 | 已有契约测试；缺显式契约版本号。harness 维护者 |
| provider 健康与失败关闭 | 满足 | 满足 | **缺** | `pgPortfolio` 没有 `health()`。harness 维护者 |
| Cordis 依赖注入 | 满足 | 满足 | 满足 | — |
| 外部资源归插件生命周期管理 | 满足 | 满足 | 满足 | — |
| 工具权限/权益门控 | 部分 | 部分 | 部分 | 只有服务端权益；是否加 DSH 权限规则待定。harness 维护者 |
| UI 来自 Harness 客户端插件 | 缺 | 缺 | 部分 | 行情/Market Wire 没有 UI 插件；持仓、历史、连接管理页面仍是 legacy。各领域插件负责人 |
| 后台任务归插件 | 缺 | 缺 | 缺 | 快照缓存、新闻抓取、NAV 同步 worker 仍在 FastAPI。各领域插件负责人 |
| 重启/重连测试 | 部分 | 部分 | 部分 | 只覆盖挂载、卸载、重挂；缺真实 Host 重启。负责 DSH 集成的工作会话 |
| 可观测性（插件 + provider + trace） | 缺 | 缺 | 缺 | provider 不转发 `traceparent`/`X-Request-Id`。harness 维护者 |
| 金融/安全不变量 | 满足 | 满足 | 满足 | — |
| 对等测试覆盖 | 部分 | 部分 | 部分 | market 的 `/data-capabilities`、`/global`、`/intelligence`，news 的真实金样，portfolio 的连接器、OAuth、同步路由都没有 Harness 对应；legacy 把未知 mark price 压成 0，需要 legacy 侧改成 null |
| HTTPS E2E 产物 | 缺 | 缺 | 缺 | 需要 staging 上的 DSH 入口跑出的产物（**需用户决定 staging 与模型 key**） |
| 部署镜像 sha256 | 缺 | 缺 | 缺 | 生产部署方（**需用户决定部署时间**） |
| 人工审阅（reviewedBy/verifiedAt） | 缺 | 缺 | 缺 | 能力负责人 |

统计（`retirement-check` 输出）：market.py 4/14、news.py 4/14、portfolio.py 3/14。

---

## 4. 视觉与可用性（Round 5 未完成项）

### 4.1 手机历史抽屉焦点缺陷（`430120e`）

- **现象**：生产构建（`next build` + `next start`）下，在手机历史抽屉里选择会话后，焦点没有回到 `chat-history-trigger`。chromium 与 mobile-chrome 都复现；`next dev` 下通过。
- **根因**：选择会话会导航到 `/chat/<id>`，App Router 为新的 `[conversationId]` 段重新挂载页面，`closeMobileHistory()` 刚聚焦的触发按钮随旧树一起被丢弃（`layout-router.js` 的 ScrollAndFocusHandler 随后对新段执行 `focus()`），焦点于是落到 `<body>`。生产构建里路由已预取，导航立即提交；dev 的 RSC 往返较慢，断言恰好先通过了。这是线上真实存在的可访问性缺陷。
- **修复**：选择会话时在模块作用域记录一个 5 s 内有效的“归还焦点”意图，新的 `AgentChat` 实例挂载后消费它并聚焦自己的触发按钮。断言没有放宽。
- **CI**：`web-e2e.yml` 新增 `production-build` job，在 `next build` + `next start`（离线 fixture API）上跑 `agent-session-reliability.spec.ts` 与 `route-audit.spec.ts`。

### 4.2 Round 5 计数（`node scripts/frontend/ui-density-counts.mjs`）

统计范围是 `apps/web/{app,components,lib,plugins}` 下的 `*.ts(x)`。`border` 只统计宽度类工具（`border`、`border-t`、`border-x-2`、`border-[0.5px]` 及其变体），不统计 `border-border-pg` 这类颜色工具。审计里的 818 统计的是带边框元素，口径相同。

| 指标 | 改前（`913ba27`） | 改后 | 目标 | 提交 |
| --- | ---: | ---: | ---: | --- |
| raw `<button` | 229 | **60** | ≤ 80 | `2009149` |
| `<Button>` | 13 | 182 | — | `2009149` |
| `text-[Npx]` | 158 | **6** | 0 | `332f93a`、`27dc922`（6 处都在架构缩略图里，见下文） |
| border 宽度工具类 | 804 | **559** | ≤ 450（**未达成**） | `5915872`、`27dc922` |
| 圆角档位 | 10/14/20 + Tailwind 8/12/14/18/24/30 | **6/8/12** | 6/8/12 | `622c9d4` |
| 字号档位 | 158 处任意值 | **8 档**（11/16 … 24/32） | 8 档 | `622c9d4`、`332f93a` |
| 按钮尺寸 | 只有一种（min-h-10） | sm/md/lg = 32/40/44 px | 3 档 | `622c9d4` |

做法（脚本都在 `scripts/frontend/`，可复跑）：

- **Button**：4 个变体 × 3 种尺寸，外加 `iconOnly`，转发 ref，保留 `focus-visible` 描边。只有 secondary 画边框，所以切换变体不会改变布局尺寸。没有 `tailwind-merge`，因此按分组让调用处的类覆盖默认值：分组为 display、items、gap、字重、justify、圆角、高度、宽度、内边距、字号，只看不带前缀的类，`lg:hidden` 不会去掉基础的 `inline-flex`。sm 取 32 px，而不是 Round 5 文档的 36 px，这样控制台里的紧凑控件转换后不会变高。
- **按钮收敛**（`convert-raw-buttons.mjs`，基于 TS AST）：
  - 只转换 className 为静态字符串的按钮；
  - 保留调用处的几何类，布局不动；只删除现在由变体负责的颜色、边框和过渡类；
  - 所有属性原样保留（`type`、`aria-*`、`data-testid`、`title`、`ref`、事件），所以按 role/name 的 E2E 选择器不变；
  - 动态类（选中态、开关）和特殊配色（warning、accent、遮罩）保持 raw；
  - import 按 AST 插入。第一版按文本插入时，把 import 插进了 `api-docs-embed` 展示给用户的 Node 代码示例里；拆分提交前已修正并重做，提交历史里没有这个错误。
- **字号**：7–11 px 映射到 `text-11`（10 px 及以下不在刻度上），13/14/16/18/20/24 映射到同名档位，每档都带配对行高。
- **边框**（`reduce-nested-borders.mjs`）：
  - 嵌套在另一个中性边框盒子（或 Card、ResearchCard、TerminalPanel）里的中性全边框去掉；该盒子没有底色时补上 muted 底色，分组仍然可见；
  - 带 muted 底色的“井”去掉边框，底色已经起到分组作用；
  - 控件（input、select、textarea、button、a、summary）、分隔线（border-b/-t）、状态色边框和动态类一律不动；
  - Card、ResearchCard 原本边框 + 抬升阴影叠加，按 Round 5 规则 5 只保留阴影。
  - 没有用“环形阴影替换 border”的办法压计数：那样线条没有减少，只是换了个写法。
- **唯一例外**：首页的架构“电脑”缩略图（`trading-architecture.tsx`）是按比例缩小的插图，标签本来就是 7–9 px，而且 `architecture-visual.spec` 固定了节点位置。把它的标签改成 `text-11` 后，Notifications 节点的相对 y 从 0.88 变成 0.81，两个项目都失败。因此恢复原样，并在代码里注明这是字号刻度的例外（`27dc922`）。

### 4.2.1 顺带修复：NAV 缺失显示为 $0.00（`cbd5293`）

fixture 截图里发现仪表盘的 “PORTFOLIO / NAV” 卡片在 “No investment account connected” 旁边显示 **$0.00**（见 `assets/harness-repro-visual-20261029/fixture-desktop-light-dashboard-before-nav-fix.png`）。原因如下：
- legacy `/portfolio` 返回 `{connected: false, nav: 0}`，API 客户端读取失败时的兜底值也是这个；
- `portfolio-nav.tsx` 只把 `null` 当作缺失；
- `today-activity.tsx` 用 `nav ?? 0`，还把负 NAV 截成 0。

两处现在都显示 “—”，并标 `data-state=unavailable`；只有已连接的快照带有有限 NAV 时才显示金额。`dashboard.spec` 新增 2 例，覆盖两张卡片和已连接的情况。

### 4.3 截图与预览站对比（视觉假设）

没有测试账号（需要用户提供）。登录后页面的截图使用仓库 fixture（`pg_session=playwright-fixture-session`，离线 fixture API，浏览器只能解析回环地址），**仅作视觉假设，不代表线上真实数据**。没有访问生产 API，也没有访问预览站。

本机共截了 24 张（6 页 × 桌面/手机 × 浅色/深色，生产构建），仓库只收录 4 张代表图，放在 `docs/architecture/assets/harness-repro-visual-20261029/`：
- 桌面浅色仪表盘：NAV 修复前，用作缺陷证据；
- 桌面深色 Chat；
- 手机浅色 Memory；
- 手机深色中文账户页。

与预览站的逐页对比要等测试账号到位后再做。

### 4.4 验证

见 §5 测试证据。

---

## 5. 测试证据（本机实测）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| Harness 全量 check（干净冻结安装后） | `(cd harness && pnpm run check)`（heavy 锁 + 2000M scope） | 132 通过 / 0 失败 / 3 跳过（caddy、docker 的 live 用例，本机无二进制） |
| 冻结安装 | 删除全部 `node_modules` → `pnpm install` → 再删 → `pnpm install --frozen-lockfile` | 成功，lockfile 逐字节相同 |
| GitHub CI（harness-v2，冻结安装） | run `40878982951` | 通过 |
| 真实 DSH | `dsh puregamma [--patch resource-views.patch.yml] --dump-config` | 见 §1.4 |
| 路由表守卫 + 对等 pytest | `pytest tests/harness`（`TZ=UTC` 与 `TZ=Asia/Shanghai` 各跑一次） | 119 通过（含实时 uvicorn ↔ Harness） |
| ruff（CI 规则） | `ruff check apps packages services scripts tests --select E9,F63,F7,F82` | 通过 |
| web typecheck / lint | `pnpm --dir apps/web typecheck` / `lint` | 通过 / 9 个已有警告 |
| 全量 pytest | `pytest tests`（heavy 锁 + 2000M scope，合并 main 后） | 1530 通过、9 跳过、4 xfailed、0 失败。第一次运行时 W3 新增的 `tests/contract/test_mobile_agent_contract.py::test_a_reopened_conversation_names_its_active_run_and_pending_approvals` 失败过 1 次，单独运行和之后两次全量运行都通过，属于偶发，已告知协调者 |
| Playwright 第 1 批（生产构建 `next build` + `next start`，chromium + mobile-chrome，`--workers=1`） | agent-session-reliability、chat-design、contrast-audit、visual-style、markdown-render、theme-system、mobile-nav、mobile-fixes、live-chat-workspace | 134 通过、0 失败、4 跳过（含抽屉焦点用例，两个项目都通过） |
| Playwright 第 2 批（其余 23 个 spec，含 route-audit） | 同上 | 324 通过、8 失败、6 跳过。失败项：live-trading.spec 的 2 例 × 2 项目、plugins-runtime.spec 1 例 × 2 项目，都依赖只在 `NODE_ENV=development` 下存在的诊断钩子（`plugins/core/runtime.tsx`），属已知情况；architecture-visual 1 例 × 2 项目由本轮字号改动引起，已用 `27dc922` 修复 |
| Playwright 复跑（修复后重新构建） | architecture-visual + agent-session-reliability | 36/36 通过 |
| Playwright 复跑（NAV 修复后重新构建） | dashboard、portfolio、route-audit、architecture-visual | dashboard 新增用例修正选择器后 8/8；其余 126 通过（route-audit 两种语言 × 两个项目全部通过） |

---

## 6. 回滚

每项都是独立提交，可以单独 revert：

- 资源视图：revert `753a23e`、`358f0ad`；或者不加载 `resource-views.patch.yml`（默认就是不加载）。
- `/api` 前缀：revert `5f5569c`（不建议，revert 后这些 provider 会恢复成全部 404）。
- lockfile：revert `26826a5`，CI 回到 `--no-frozen-lockfile`。
- Portfolio/Market provider 修复：revert `0947b96`（会恢复“全部不可用”的缺陷）。
- 对等测试与 candidates：revert `1563c5d`；`retired` 本来就为空，不影响任何路由。
- 抽屉焦点：revert `430120e`。
- NAV 显示：revert `cbd5293`（会恢复 $0.00 的显示）。
- 视觉：按 `5915872` → `2009149` → `332f93a` → `622c9d4` 的顺序 revert；每一步之后 typecheck 都通过。

## 7. 遗留项

- border 559，未达到 ≤ 450。剩下的主要是顶层卡片的中性边框（约 70 处，`bg-bg-panel rounded-xl border`）和动态类。前者要定设计：去掉边框后卡片与页面底色的对比在亮色主题下偏弱，需要先确定卡片用 0.5 px hairline 还是只用抬升阴影；后者需要逐个组件手改。
- raw `<button>` 剩 60 个，都是动态类（选中态、开关）或特殊配色（status-warning、遮罩），需要给 Button 增加 `selected`/`tone` 能力后再收敛。
- 资源视图没有在真实 DSH Host 的浏览器里端到端打开过（见 §1.4）。
- 退役门槛的缺口见 §3.3。没有任何 surface 可以退役。
- legacy `/portfolio` 把未知的 mark price 压成 0，Harness 无法区分；需要 legacy 侧改为 null，web UI 也要配合。

## 8. 需要用户拍板的事项

- 测试账号（用于登录后页面与预览站的逐页对比）。
- staging 环境与真实模型 key（用于退役证书的 HTTPS E2E 产物）。
- 生产部署时间（退役证书需要部署镜像 digest）。
- 卡片边框的设计取舍（hairline 还是只用阴影），决定 border 计数能否降到 ≤ 450。
- 是否把 GitHub 默认分支改为 `main`（沿用上一轮的待决项）。
