# private-PM 数据契约

核对基线：分支 `server/pm-live-20260916`。本文涉及的 PM 文件在 `83b753b` 上逐行核对（其后的 `0425831` 未改动任何 PM 文件）。
两个 schema 常量定义在 `apps/api/services/pm_riskbot_service.py` 第 37–38 行：

```python
LATEST_SCHEMA = "puregamma.pm_account.v1"
SERIES_SCHEMA = "puregamma.pm_nav_series.v1"
```

生产者是 riskbot（不在本仓库）；消费者是 PureGamma API 与本仓库的 Web 面板。本文只承诺**读取器实际读/校验/返回**的东西，其余部分明确标为透传。

> **English summary** — Two bundle schemas exist: `puregamma.pm_account.v1` (`latest.json`) and `puregamma.pm_nav_series.v1` (`series.json`). This document describes exactly what the reader validates, projects and returns; anything else is explicit pass-through.

---

## 1. `latest.json` — `puregamma.pm_account.v1`

读取入口：`PmAccountReader.latest()` → `_read("latest.json", LATEST_SCHEMA)`（第 142–143 行）。

### 1.1 读取器**校验**的输入字段

| 字段 | 校验方式 |
| --- | --- |
| `schema` | 必须**完全等于** `"puregamma.pm_account.v1"`；否则拒收，`reason: "unsupported bundle schema '<实际值>'"`（第 133–137 行） |

除此之外，读取器只在顶层必须是 JSON **对象**这一点上做类型检查（第 131–132 行，失败为 `bundle is not an object`）。

### 1.2 读取器**读取**的输入字段

| 输入字段 | 用途 |
| --- | --- |
| `generated_at` | 作为 `generated_at` 返回；当 `snapshot.captured_at` 缺失时充当 `data_as_of` |
| `snapshot.captured_at` | `data_as_of` 首选值 |
| `snapshot.captured_at_ms` | `_age_seconds` 在 mtime 缺失时的兜底 |
| `snapshot.is_stale` | 与 mtime 年龄取**或**，决定 `stale` |
| `snapshot.partial` | 与 `quality.partial` 取**或**，决定 `partial` |
| `quality.partial` | 同上（注意：它影响 `partial`，但**不会**出现在返回的 `quality` 里） |
| `collector` | 透传为 `collector`，并用于推导 `source.collector` / `source.read_only` / `source.independent_of_trading_bot` |
| `account` / `btc` / `exposure` | 原样透传（`or {}` 兜底） |
| `balances` / `positions` / `positions_history` / `orders` / `protection` | 原样透传（`or []` 兜底） |
| `positions_history_meta` | 原样透传（`or {}` 兜底） |
| `orders_meta.*` | **白名单投影**，见 1.3 |
| `risk.*` | **白名单投影**，见 1.3 |
| `coverage.*` | **白名单投影**，见 1.3 |
| `quality.*` | **白名单投影**，见 1.3 |
| `disclaimer` | 原样透传 |

> 透传的含义：读取器不校验这些容器内部的字段名与类型，风险bot 写什么客户端就收到什么（内层新增字段会自动到达客户端）。`account` / `btc` / `exposure` 缺失时返回空对象 `{}`，`balances` 等缺失时返回空数组 `[]`——**因此响应本身无法区分"字段缺失"和"字段为空"**。

> **数字一律是字符串**：bundle 中每个数值都以字符串给出（`packages/decisions/redaction.py` 的注释：`The bundle stores every figure as a string`；`pm-account-panel.tsx` 的 `num()` 也按此窄化）。消费方必须解析后使用，**解析失败按缺值处理并显示 `--`，不得回落成 0**——这与读取器"不编造"的不变量是同一条纪律。

> **消费者不止一个**：`account_view()` 目前有两个消费者——Web 面板 `apps/web/components/pm-account-panel.tsx`，以及决策层的 `packages/decisions/redaction.py` → `redact_account_view`（输出 schema `puregamma.pm_judgment_state.v1`，在数据交给第三方模型前按字段 allowlist 投影，默认丢弃未列名字段）。因此"透传即自由"只对 Web 端成立：任何要离开本进程的结构都必须被显式列入 redaction 的 allowlist。

### 1.3 四个白名单投影（未列出的键会被丢弃）

`orders_meta`（第 196–201 行）：

| 字段 | 默认 |
| --- | --- |
| `captured_at` | `null` |
| `age_seconds` | `null` |
| `fully_covered` | `null` |
| `refresh_interval_seconds` | `null` |

`risk`（第 203–208 行）：

| 字段 | 默认 |
| --- | --- |
| `firing_count` | `0` |
| `firing` | `[]` |
| `drawdown_peak_btc_equivalent` | `null` |
| `drawdown_day_btc_equivalent` | `null` |

`coverage`（第 209–214 行）：

| 字段 | 默认 |
| --- | --- |
| `essential_ok` | `null` |
| `orders_covered` | `null` |
| `failures` | `[]` |
| `essential_failures` | `[]` |

`quality`（第 215–220 行）：

| 字段 | 默认 |
| --- | --- |
| `rest_ok` | `null` |
| `ws_connected` | `null` |
| `mismatch` | `null` |
| `last_error` | `null` |

> **English summary** — The reader validates only the top-level `schema` string plus "top level is a JSON object". `account`/`btc`/`exposure`/`balances`/`positions`/`positions_history`/`orders`/`protection`/`positions_history_meta` are passed through untouched, so absent and empty are indistinguishable; `orders_meta`, `risk`, `coverage` and `quality` are whitelist-projected with the defaults above, and `quality.partial` is consumed but never echoed.

---

## 2. `account_view()` 返回字段（成功分支）

`GET /portfolio/pm` 在通过授权闸门后返回 `account_view()`，路由另外补两个键（`portfolio.py` 第 232–236 行）。下表的字段名全部与代码逐字核对（实际返回 23 个键 + 路由补的 2 个）：

| 字段 | 类型 | 来源 / 说明 |
| --- | --- | --- |
| `available` | `bool` | 恒为 `true`；不可用分支见第 3 节 |
| `stale` | `bool` | `mtime 年龄 > STALE_AFTER_SECONDS` **或** `snapshot.is_stale` |
| `partial` | `bool` | `snapshot.partial` **或** `quality.partial` |
| `age_seconds` | `float \| null` | 由 `_age_seconds(snapshot, mtime)` 计算，即"本进程时钟 − 文件 mtime"，`max(0.0, …)` |
| `stale_after_seconds` | `float` | 即 `STALE_AFTER_SECONDS = 180.0`；随响应下发，前端不硬编码 |
| `data_as_of` | `str \| null` | `snapshot.captured_at`，缺失则 `generated_at` |
| `generated_at` | `str \| null` | bundle 顶层的 `generated_at` |
| `collector` | `dict` | bundle 顶层的 `collector`，原样透传 |
| `source` | `dict` | 构造值：`collector`（默认 `"riskbot"`）、`read_only`（默认 `true`）、`independent_of_trading_bot`（默认 `true`）、`venue` 恒为 `"Binance Portfolio Margin (Classic)"`、`note` 为中文说明"只读采集，PureGamma 不持有该账户的任何 API Key，也不具备下单/撤单能力" |
| `account` | `dict` | 交易所官方口径字段，**保留原名**（注释：`Official exchange figures, kept names intact.`）；`account.*_derived` 为本地派生字段 |
| `btc` | `dict` | 真实 BTC 数量 vs. USD 数字的 BTC 等值（注释：`Real BTC quantity vs BTC-equivalent of USD figures.`） |
| `exposure` | `dict` | 敞口，原样透传 |
| `balances` | `list` | 逐币种余额，原样透传 |
| `positions` | `list` | 当前持仓，原样透传 |
| `positions_history` | `list` | 仓位生命周期事件，**由相邻快照差分得到，最新在前**（注释：`Position lifecycle history (snapshot-diff derived, newest first).`） |
| `positions_history_meta` | `dict` | 原样透传（Web 端类型含 `kind` / `note` / `limit` / `count` / `first_event_at`） |
| `orders` | `list` | 当前挂单，原样透传 |
| `orders_meta` | `dict` | 见 1.3 白名单投影 |
| `protection` | `list` | 保护性挂单覆盖情况，原样透传 |
| `risk` | `dict` | 见 1.3 白名单投影 |
| `coverage` | `dict` | 见 1.3 白名单投影 |
| `quality` | `dict` | 见 1.3 白名单投影 |
| `disclaimer` | `str \| null` | 原样透传 |
| `label` | `str` | **路由**补入：`settings.pm_account_label` |
| `merged_into_portfolio_nav` | `bool` | **路由**补入：恒为 `false`（该账户是两位用户共享的单一数据源，并入会重复计算） |

注意 `GET /portfolio/pm/history` **只有** `nav_history_view()` 的内容，不带 `label` / `merged_into_portfolio_nav`。

### 2.1 内层字段（`account` / `btc` / `exposure`）

这三个 bag 由 riskbot 定义（生产者不在本仓库），读取器原样透传。下表列出**当前客户端实际消费**的字段名，来源为 `apps/web/lib/api.ts`（第 1203–1230 行类型定义）与 `pm-account-panel.tsx` / `portfolio-console.tsx` 的取值代码；未在此列出的内层字段属于透传面，本契约不作保证：

| bag | 字段 | 消费位置 |
| --- | --- | --- |
| `account` | `adjusted_equity_usd` | 面板 hero 与"调整后权益"（官方 `actualEquity` = 市值 − 负债） |
| `account` | `account_equity_usd` | 次级指标"购买力基准"、组合页 PM 摘要行的"净值" |
| `account` | `equity_btc_equivalent` | 官方 `accountEquity ÷ BTCUSDT` |
| `account` | `total_available_balance_usd` / `available_btc_equivalent` | "可用资金"指标 |
| `account` | `total_unrealized_pnl_usd` | "未实现盈亏"（缺失时退化为逐币种 `unrealized_pnl` 求和） |
| `account` | `uni_mmr` | "官方 uniMMR"（乘 100 显示为百分比） |
| `account` | `account_maint_margin_usd` / `maint_margin_usage_derived` | "维护保证金"及其占权益比 |
| `account` | `account_initial_margin_usd` / `equity_buffer_derived` | "初始保证金"与"权益缓冲" |
| `btc` | `quantity` | 面板注释：官方 `totalWalletBalance`（真实持币量）；组合页摘要"BTC 持仓" |
| `btc` | `price_usd` | BTC 计价与 USD↔BTC 换算的汇率 |
| `btc` | `collateral_value_usd` | 抵押价值展示 |
| `exposure` | `gross_notional_usd` / `gross_notional_btc_equivalent` | "总敞口（gross）" |

命名纪律（`portfolio.py` 文档字符串）：官方字段与本地派生字段分列在 `account.*` 与 `account.*_derived` 两个键下，**派生值不得被称作官方值**。面板同样用代码注释固定了这一点（第 27–28 行："Never show one of these numbers under another's label, and never call a derived figure 'official'."）。

> **English summary** — The success payload has 23 keys plus the two added by the route (`label`, `merged_into_portfolio_nav: false`). Exchange-official figures keep their names in `account.*`, locally derived ones end in `_derived`, and the real BTC quantity in `btc.quantity` is kept apart from BTC *equivalents* of USD figures. Inner bag fields are riskbot's; the table lists only the ones the current clients actually consume.

---

## 3. `account_view()` 不可用分支

bundle 无法使用时**只**返回下面这些键（第 152–158 行；`GET /portfolio/pm` 另加 `label`、`merged_into_portfolio_nav`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `available` | `bool` | `false` |
| `reason` | `str` | 失败原因（取值见 `ARCHITECTURE.md` 失败模式表） |
| `source` | `dict` | 仅 `{"collector": "riskbot", "read_only": true}` |
| `bundle_path` | `str` | 读取器尝试读取的绝对路径，便于排障 |

**没有任何 `account` / `balances` / `positions` / `orders` 键**——不可用时不存在"零值占位"。

> **English summary** — The unavailable shape is `{available: false, reason, source, bundle_path}` (+ route-level `label` / `merged_into_portfolio_nav`), with no numeric fields and no zero placeholders.

---

## 4. `series.json` — `puregamma.pm_nav_series.v1` 与 `nav_history_view()`

读取入口：`PmAccountReader.series()` → `_read("series.json", SERIES_SCHEMA)`（第 145–146 行）。校验规则与第 1.1 节完全相同（顶层 `schema` 必须逐字相等）。

### 4.1 返回字段（成功分支）

| 字段 | 类型 | 来源 / 说明 |
| --- | --- | --- |
| `available` | `bool` | `true` |
| `schema` | `str` | bundle 顶层的 `schema`（即 `"puregamma.pm_nav_series.v1"`） |
| `generated_at` | `str \| null` | 原样透传 |
| `first_point_at` | `str \| null` | 首个观测点的时刻 |
| `point_count` | `int` | 顶层 `point_count`；缺失时退化为 `len(points)` |
| `sufficient` | `bool` | **由读取器计算**：`len(points) >= 2` |
| `window_days` | `int \| null` | 原样透传 |
| `interval_hint_seconds` | `int \| null` | 原样透传 |
| `sampling` | `str \| null` | 原样透传 |
| `points` | `list` | **原样透传，不插值、不补点、缺口保留** |

### 4.2 `sufficient` 为什么存在

代码注释（第 242 行）原文：

> Reported so the UI can say "数据不足" instead of drawing one dot.

路由文档字符串（`portfolio.py` 第 241–246 行）进一步规定：

> `sufficient` is false until at least two observations exist; the UI must show "数据不足" rather than interpolate a curve, so no point is ever synthesised here.

即：**一个点画不出趋势**，用 1 个点连成"曲线"是在制造不存在的形状。因此 `sufficient` 用实际点数（`len(points)`，不是可能滞后的顶层 `point_count`）计算，少于 2 就为 `false`，前端据此显示"数据不足"而不是画线。

已实测：`points` 为 1 个点时返回 `sufficient: false`；2 个点时 `true`。

前端还多一层保险：即使 `sufficient` 为真，只要当前币种（USD/BTC）下**可用值**少于 2 个（`usable.length > 1`）也不画图（`pm-account-panel.tsx` 第 338、406–412 行），例如 `adjusted_equity_usd` 为空的点不会被当成值。

### 4.3 不可用分支

`available: false`、`reason`、`points: []`、`point_count: 0`、`interval_hint_seconds: None`（第 226–233 行）。注意这个分支**不含** `schema` / `sufficient` / `window_days` / `sampling` 等键——消费方必须先判断 `available`。

### 4.4 观测点字段

`points` 的元素由读取器整体透传。客户端类型（`apps/web/lib/api.ts` 第 1231–1245 行，`?` 表示可能缺省）为：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `t` | `number` | 观测时刻（Unix 秒） |
| `equity_usd` | `string \| null` | 官方 `accountEquity` 口径（保证金基准） |
| `adjusted_equity_usd` | `string \| null`（可选） | 官方 `actualEquity`＝市值 − 负债；**曲线与 hero 都读它** |
| `equity_btc_equivalent` | `string \| null` | 权益的 BTC 等值 |
| `btc_price_usd` | `string \| null` | 该点使用的 BTC 价格（用来把 USD 折算成 BTC 画图） |
| `btc_quantity` | `string \| null` | 该点真实 BTC 数量 |
| `btc_collateral_usd` | `string \| null`（可选） | BTC 抵押价值 |
| `available_usd` | `string \| null`（可选） | 可用资金 |
| `gross_notional_usd` | `string \| null`（可选） | 总敞口 |
| `net_notional_btc_equivalent` | `string \| null`（可选） | 净敞口 BTC 等值 |
| `positions` / `orders` / `degraded` | `number`（可选） | 该点的仓位/挂单/降级计数 |

**曲线必须与 hero 同口径**：面板把 hero 与曲线都绑到 `adjusted_equity_usd`（第 174–186、262–272 行）。历史实现曾让两者读不同字段而"按设计地不一致"，代码注释明确禁止再发生：

> They must not diverge - an earlier version showed a per-asset derived figure in the hero and accountEquity in the curve, and the two disagreed by design.

> **English summary** — `nav_history_view()` echoes `points` exactly as observed (no interpolation, gaps kept) and adds `sufficient = len(points) >= 2`, which exists purely so the UI can say "not enough data" instead of drawing a one-dot curve; the client additionally requires two *usable* values in the selected currency. The curve and the hero both read `adjusted_equity_usd` (official `actualEquity`), and the code forbids letting them diverge.

---

## 5. 契约变更规则

1. **schema 是唯一的版本闸门，读取器不猜测。** 顶层 `schema` 与期望值不逐字相等时，读取器**拒收整个 bundle**（`data = None`）、记 `logger.warning`，并让接口返回 `available: false` + `reason: "unsupported bundle schema '<实际值>'"`。它不会尝试按旧规则解析新文件，也不会退回上一次的好数据（因为 mtime 已变，缓存不命中）。
2. **拒收优于错值。** 拒收的后果是页面显示"数据不可用（原因）"；猜测的后果是用户看到**看起来正确的错误数字**。代码在两者之间明确选择了前者（不变量 2）。
3. **破坏性变更必须提升 schema 版本号**：重命名、改口径、改单位、改 `account.*` 与 `account.*_derived` 的归属，都属于破坏性变更——先改成 `puregamma.pm_account.v2` / `puregamma.pm_nav_series.v2`，再同步升级读取器常量（`LATEST_SCHEMA` / `SERIES_SCHEMA`）。
4. **纯新增字段不需要改版本号**：内层 bag 与 `points` 是透传，生产端新增字段会自动到达客户端（客户端类型可选，按需消费）；顶层容器新增键需要读取器显式转发才会出现。白名单投影的四组对象（`orders_meta`/`risk`/`coverage`/`quality`）新增键**不会**自动透出。
5. **灰度期不可能两端各写一半**：读取器每个 schema 只认一个版本，schema 不匹配即拒收。因此切换顺序必须是"先让生产端同时能写新版本 → 再升级读取器 → 再停旧版本"，不能反过来。
6. **不要用 `snapshot.age_seconds` 做新鲜度判断**：读取器已明确忽略它（见 `ARCHITECTURE.md` 4.2）。需要表达"采集层知道数据旧了"时用 `snapshot.is_stale`。
7. **不要假设透传字段存在**：`account.*` 与 `points[].*` 的字段缺失表现为 `undefined`/缺键，消费方必须像现有面板那样用 `num()` 之类的窄化函数处理，缺值显示 `--` 而不是 0。

> **English summary** — Contract changes: the top-level `schema` is the only version gate and a mismatch is rejected loudly (`unsupported bundle schema …`) rather than guessed around, because a rejection degrades to "unavailable" while a guess shows plausible wrong numbers. Breaking changes require a new schema version and a matching reader constant; additive fields are safe only inside pass-through containers, not inside the four whitelist-projected objects.
