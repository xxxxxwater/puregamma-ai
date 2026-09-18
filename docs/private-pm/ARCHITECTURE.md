# private-PM 架构（Binance Portfolio Margin 只读看板）

适用范围：私有 Binance Portfolio Margin（PM）账户在 PureGamma 中的**只读**展示链路。
核对基线：分支 `server/pm-live-20260916`。本文涉及的 PM 文件在 `83b753b` 上逐行核对（其后的 `0425831` 未改动任何 PM 文件）。所有结论均直接来自下列文件的代码与文档字符串，未作推测：

| 关注点 | 文件 |
| --- | --- |
| 读取器 / 不变量 / 缓存 / 新鲜度 | `apps/api/services/pm_riskbot_service.py`（283 行） |
| 路由与授权挂载点 | `apps/api/routers/portfolio.py`（`GET /pm`、`GET /pm/history`） |
| 服务端授权闸门 | `apps/api/dependencies.py` → `require_pm_account_viewer` |
| 配置项 | `apps/api/config.py`（`pm_riskbot_export_dir` / `pm_account_allowed_emails` / `pm_account_label`） |
| 展示层 | `apps/web/components/pm-account-panel.tsx`（554 行）、挂载点 `apps/web/components/portfolio-console.tsx` |
| 部署保留 | `deploy/pm-paths.txt`、`deploy/pm-preserve.sh` |

> **English summary** — Scope and verification baseline. Every statement below is sourced from the listed files at commit `83b753b`; nothing is inferred.

---

## 1. 数据流是单向的（设计核心）

模块文档字符串（`pm_riskbot_service.py` 第 3–13 行）原文给出的链路是：

```
Binance  ---->  riskbot  ---->  export bundle  ---->  PureGamma API  ---->  UI
                (owns the        (JSON files,          (this module;
                 read-only        atomically           never holds an
                 API key)         replaced)             exchange key)
```

逐段说明：

1. **Binance PM 账户** — 唯一的真相来源。账户口径的字段（`account.*`）由交易所给出，PureGamma 不重算、不改名（`account_view` 中注释："Official exchange figures, kept names intact."）。
2. **riskbot** — 独立采集器，**持有该账户的只读 API Key**。它按约 60s 一次对账（`STALE_AFTER_SECONDS` 注释：`riskbot reconciles every 60s`）。
3. **导出 bundle** — riskbot 写入的 JSON 文件：`latest.json`（账户快照）与 `series.json`（NAV 时序）。写入方式是 **tmp + rename 原子替换**（`_read` 中的注释："A torn read cannot happen (riskbot writes tmp+rename)"），因此读取器永远看不到半个文件。
4. **PureGamma API（本模块）** — 只读这个目录。目录由 docker 以 `:ro` 挂载（`docker-compose.production.yml` 第 177 行），PureGamma **不持有任何该账户的交易所凭证**。
5. **UI** — `PmAccountPanel` 渲染官方口径数字与真实快照曲线；PM 账户作为**独立数据源**展示，`merged_into_portfolio_nav` 恒为 `false`。

对外只有两个只读端点（`apps/api/routers/portfolio.py`，router `prefix="/portfolio"`，`main.py` 未再加前缀）：

| 方法 | 路径 | 处理函数 | 返回 |
| --- | --- | --- | --- |
| GET | `/portfolio/pm` | `get_pm_account` | `account_view()` + `label` + `merged_into_portfolio_nav: false` |
| GET | `/portfolio/pm/history` | `get_pm_nav_history` | `nav_history_view()` |

**不并入组合净值**是刻意的：该账户是两位授权用户共享的**单一数据源**，按用户累加会把同一份余额重复计算（`portfolio.py` 第 215–217 行；`portfolio-console.tsx` 第 247–249、267 行同义注释）。

> **English summary** — One-way flow: Binance → riskbot (read-only key) → atomically replaced JSON bundle → PureGamma API (no exchange credentials) → UI. Only two read-only endpoints exist (`/portfolio/pm`, `/portfolio/pm/history`), and the PM account is deliberately never merged into the aggregated portfolio NAV, because it is a single source shared by two users.

---

## 2. 两条硬不变量

### 2.1 授权在服务端：`allowed_emails()` 是唯一真相来源

模块文档字符串（第 17–19 行）原文：

> **Authorization is server-side.** `allowed_emails()` is the single source of truth and every route that touches PM data depends on it; hiding UI is never treated as access control.

代码落点：

- `allowed_emails()`（第 51–62 行）从 `PM_ACCOUNT_ALLOWED_EMAILS` 读取，按 `;` 与 `,` 分隔、`strip()`、小写化（`normalize_email`）、去重（`dict.fromkeys` 保序），返回 `tuple[str, ...]`。
- `is_allowed_email()`（第 65–69 行）：空邮箱直接 `False`；否则要求命中白名单。
- `require_pm_account_viewer`（`dependencies.py` 第 136–160 行）：依赖 `get_current_user`，用 `is_allowed_email(user.email)` 判定，失败时记 `pm_account_access_denied` 警告（含 `allowlist_size`）并抛 **403**：

  ```json
  {"detail": {"code": "PM_ACCOUNT_NOT_AUTHORIZED",
              "message": "This account is not authorized to view the private portfolio."}}
  ```

- 两个路由（`get_pm_account`、`get_pm_nav_history`）**都**把 `_user: User = Depends(require_pm_account_viewer)` 作为依赖，因此**整个 payload**（含 balances/positions/orders/history）都在闸门之后，没有逐字段过滤。

"隐藏 UI 不算访问控制"在三处被重复声明，本文件不再重复造词：

- `pm_riskbot_service.py`：`hiding UI is never treated as access control`；
- `dependencies.py`：`Hiding a link in the UI is presentation, not authorization: a crafted request from any other logged-in account is rejected here.`；
- `portfolio.py`：`A UI that hides the section is not access control.`

前端只是**表现层**的配合：`portfolio-console.tsx` 捕获 403 并把 `reason` 置为 `"forbidden"`，`PmAccountPanel` 见到 `view?.reason === "forbidden"` 就 `return null`（第 227–228 行）。这是"未授权者看不到任何东西"的体验，**不是**安全边界——真正的边界是 403。

> **English summary** — Invariant 1: authorization is server-side. `allowed_emails()` is the only source of truth, every PM route depends on `require_pm_account_viewer` (403 `PM_ACCOUNT_NOT_AUTHORIZED`), and the gate covers the whole payload. The panel returning `null` on `reason === "forbidden"` is presentation only — never access control.

### 2.2 不编造：缺失或过期就报 `available: false`，绝不返回假零

模块文档字符串（第 20–22 行）原文：

> **Nothing is fabricated.** If the bundle is missing or old, the reader reports `available: false` with the reason instead of inventing zeros, and the NAV series is returned exactly as observed (gaps included).

代码落点：

- `account_view()`（第 152–158 行）：`latest.ok` 为假时立刻返回 `available: False` + `reason`，**不含**任何 `account`/`balances`/`positions` 键——不存在"用 0 填满"的分支。
- `nav_history_view()`（第 226–233 行）：同样返回 `available: False` + `reason`，并显式给出 `points: []`、`point_count: 0`、`interval_hint_seconds: None`。
- 时间序列只按**实际观测**返回：`nav_history_view` 原样转发 `payload["points"]`（第 235–247 行），不插值、不补点、不补齐缺口；`sufficient` 由 `len(points) >= 2` 计算（见 DATA_CONTRACT）。
- 读取失败/过期时**记录原因**而非吞掉：schema 不符与 JSON 损坏都打 `logger.warning`，并进入 `reason` 字符串。

前端与之后端一致：`pm-account-panel.tsx` 第 231–233 行在不可用时显示"只读账户数据暂不可用（原因）。**此处不会显示任何估算或占位数值。**"；不足 2 点时显示"数据不足：该区间至少需要 2 个真实快照（不插值、不伪造）。"（第 407–411 行）。

> **English summary** — Invariant 2: nothing is fabricated. A missing, unreadable or schema-mismatched bundle yields `available: false` with a reason and no zero-filled fields; the NAV series is echoed exactly as observed, gaps included. The UI states plainly that no estimate or placeholder is shown.

---

## 3. 为什么 PureGamma 不持有交易所 Key

安全论证来自模块文档字符串（第 10–13 行）：

> PureGamma holds **no** Binance credentials for this account: it reads files that riskbot writes into a directory mounted read-only. That keeps the trading account unreachable from the web tier and means a PureGamma compromise cannot place, cancel or transfer anything.

展开成三条可检验的结论：

1. **凭证不在 Web 层**：PM 账户的 API Key 只存在于 riskbot 侧。PureGamma 进程环境里没有该账户的 key/secret（`config.py` 第 125–129 行的注释同样写明 "PureGamma holds no exchange credentials for this account"）。
2. **写权限被文件系统剥夺**：容器以 `:ro` 挂载该目录（`docker-compose.production.yml` 第 177 行），即使 Web 层被攻破也**不能写入或篡改**采集器输出。挂载点注释原文：`Read-only on purpose: PureGamma never holds this account's exchange credentials and must never be able to write to the collector's output.`
3. **能力面本身就窄**：链路只能"读文件、算展示"。下单 / 撤单 / 划转这些动作在该模块中**没有任何代码路径**——不是被开关挡住，而是不存在。响应里也把这一点作为事实回报给客户端（`source.read_only`、`source.note`："只读采集，PureGamma 不持有该账户的任何 API Key，也不具备下单/撤单能力"）。

因此"Web 层被攻破"的最坏后果被限制在**读取一份已经由交易所审计过的只读快照**，而不是动账户资产。

> **English summary** — No exchange credentials exist in the web tier: the key lives in riskbot, the export directory is mounted `:ro`, and there is no code path in this module that could place, cancel or transfer anything. A compromised web tier can at worst read an already read-only snapshot.

---

## 4. 缓存与新鲜度策略

三个常量（`pm_riskbot_service.py` 第 40–44 行）：

| 常量 | 值 | 代码注释原文 |
| --- | --- | --- |
| `MAX_CACHE_SECONDS` | `5.0` | "Hard cap on how long a cached read may serve the response, so an operator never sees an unbounded-stale page if the file mtime is misleading." |
| `STALE_AFTER_SECONDS` | `180.0` | "Bundles older than this are reported as stale (riskbot reconciles every 60s)." |

### 4.1 缓存的命中条件

`_read()`（第 100–140 行）的进程内缓存键是 `(st_mtime, st_size, read_at)`：只有当 **mtime 未变、size 未变、且距上次读取 < `MAX_CACHE_SECONDS`** 时才复用（第 115–122 行）。任何一项不满足就重新读盘并重新校验 schema。缓存条目只在成功读取后写入（`data` 一定非空），失败不会污染缓存。

`PmAccountReader` 由模块级单例 `get_reader()`（第 269–276 行）提供，按导出目录字符串绑定；`reset_reader_cache()`（第 279–283 行）用于测试或配置重载。这意味着**每个 API worker 进程各有一份缓存**，"5 秒"是每进程的上限，不是全局的。

### 4.2 为什么 `_age_seconds` 以文件 mtime 为准，而不是 `snapshot.age_seconds`

`_age_seconds()` 的文档字符串（第 252–256 行）原文：

> Age of the observation, measured from the reader's own clock. `snapshot.age_seconds` is relative to riskbot's process clock, which is meaningless here; the file mtime is what this process can verify.

即：`snapshot.age_seconds` 是 **riskbot 进程自己的时钟**算出来的数，对 PureGamma 没有可比性——采集器容器与 API 容器的时钟可能漂移，那个数字也无法验证。本进程能验证的只有"这个文件最后被写入的时刻"，所以：

```python
def _age_seconds(snapshot, mtime):
    if mtime is not None:
        return max(0.0, time.time() - mtime)          # 首选：文件 mtime
    captured = snapshot.get("captured_at_ms")
    if isinstance(captured, (int, float)) and captured > 0:
        return max(0.0, time.time() - float(captured) / 1000.0)   # 兜底：捕获时间戳
    return None
```

已实测：把 bundle 写成 `snapshot.age_seconds = 99999`，`account_view()["age_seconds"]` 仍然 ≈ 0（按 mtime 计算，完全忽略那个字段）。

`stale` 的判定是 **两个来源的并集**（第 164、169 行）：

```python
stale = age_seconds is not None and age_seconds > STALE_AFTER_SECONDS
...
"stale": bool(stale or snapshot.get("is_stale")),
```

也就是：文件层面超过 180s → `stale`；或者采集器自己在 `snapshot.is_stale` 里承认过期 → 同样 `stale`。`stale_after_seconds` 会随响应一起返回，前端不硬编码阈值。

前端的新鲜度显示（`pm-account-panel.tsx` 第 215–222 行）：优先用 `generated_at ?? data_as_of` 由浏览器解析出年龄，解析失败才退回服务端的 `age_seconds`；阈值取 `stale_after_seconds ?? 180`；`age ≤ staleAfter` 显示 **LIVE**，否则 **STALE**。为了让徽标在两次 60s 轮询之间也不失真，组件每 15s 触发一次重算（第 168–171 行）。

> **English summary** — A read is cached for at most `MAX_CACHE_SECONDS = 5.0` and only while mtime+size are unchanged; the cache is per worker process. Freshness uses `_age_seconds`, computed from the file mtime (or `captured_at_ms` as fallback) because `snapshot.age_seconds` comes from riskbot's clock and cannot be verified here. `stale` is `age > STALE_AFTER_SECONDS (180s)` OR `snapshot.is_stale`. The UI re-derives the LIVE/STALE badge every 15s against the server-supplied threshold.

---

## 5. 失败模式表

下表每一行的 `reason` 字符串都是 `account_view()` 实际会返回的内容（已用真实调用核对）。共同点是：**四种失败都不会产生数字**，只产生原因。

| 情况 | 判定位置 | `account_view()` 返回 | UI 表现 |
| --- | --- | --- | --- |
| `latest.json` 不存在，且没有近期成功读取的缓存 | `_read` 的 `FileNotFoundError` 分支（第 105–112 行） | `available: false`，`reason: "riskbot export bundle not found"` | 不可用卡片，附原因；不显示任何数值 |
| bundle 不可读（`stat` 抛 `OSError`，例如权限/IO） | 第 113–114 行 | `available: false`，`reason: "unreadable: <异常>"` | 同上 |
| 文件存在但不是合法 JSON | 第 123–130 行（并 `logger.warning`） | `available: false`，`reason: "malformed bundle: <异常>"` | 同上 |
| JSON 合法但顶层不是对象 | 第 131–132 行 | `available: false`，`reason: "bundle is not an object"` | 同上 |
| schema 不匹配（如 `puregamma.pm_account.v2`） | 第 133–137 行（并 `logger.warning`） | `available: false`，`reason: "unsupported bundle schema '<实际值>'"` | 同上（**注意：不会退回上一次的好数据**，因为 mtime 已变） |
| 数据过期：mtime 年龄 > 180s | 第 163–164 行 | `available: true`，`stale: true`，`age_seconds` 为真实年龄 | 数字照常显示，但徽标为 **STALE** |
| 采集器自认过期：`snapshot.is_stale` | 第 169 行 | `available: true`，`stale: true` | 同上 |
| 采集不完整：`snapshot.partial` 或 `quality.partial` | 第 170 行 | `available: true`，`partial: true` | 当前面板不单独渲染 `partial`（见 DATA_CONTRACT） |
| 文件**消失**，但 180s 内成功读过一次 | 第 108–110 行 | `available: true`，继续返回**最后一次成功读取的副本**；`stale` 仍由 mtime 年龄决定 | 可能仍显示 **LIVE**，直到 mtime 年龄过 180s 或缓存窗口（自 `read_at` 起算）关闭；窗口关闭后转为 `reason: "riskbot export bundle not found"` |
| `series.json` 缺失或不可用 | `nav_history_view` 第 226–233 行 | `available: false`，`reason` 同上几种，`points: []`、`point_count: 0`、`interval_hint_seconds: None` | "历史数据暂不可用，未绘制曲线。" |
| `series.json` 可用但该区间少于 2 个点 | `sufficient` 与前端 `usable.length > 1` | `available: true`，`sufficient: false` | "数据不足：该区间至少需要 2 个真实快照（不插值、不伪造）。" |
| `PM_RISKBOT_EXPORT_DIR` 为空（功能关闭） | `get_reader()` 第 272–275 行 → `Path("/nonexistent")` | 等价于第一行：`reason: "riskbot export bundle not found"` | 不可用卡片 |
| 调用者不在白名单 | `require_pm_account_viewer` | HTTP **403** `PM_ACCOUNT_NOT_AUTHORIZED` | 前端置 `reason = "forbidden"`，面板整体 `return null`（什么都不渲染） |

补充两点容易误读的行为：

- 第 9 行的"文件消失仍在 180s 内供旧副本"是刻意设计的**短窗兜底**（注释：`Keep serving the last good copy only if it is recent; otherwise report the outage rather than a stale page presented as live.`）。它的"近期"按 `read_at` 计，而 `stale` 标记按 mtime 年龄计，两者**不是同一个时钟起点**。
- 第 3、5 行这类失败不会复用旧缓存：缓存命中要求 mtime+size 完全相同，文件被替换后必然重新读取并重新校验 schema。

> **English summary** — Failure modes are uniform: missing / unreadable / malformed / non-object / schema-mismatch all return `available: false` with a specific reason and zero numeric fields; expired data returns real numbers with `stale: true`; a vanished file is served from the last good read for at most `STALE_AFTER_SECONDS` from `read_at`; unauthorized callers get HTTP 403 and the panel renders nothing at all.

---

## 6. 边界与已知缺口（供后续变更参考）

- **契约校验只有一层**：读取器只校验顶层 `schema` 字符串；`account` / `btc` / `exposure` / `balances` / `positions` / `orders` / `protection` / `points` 都是**原样透传**，"字段缺失"与"字段为空"在响应里无法区分（见 `DATA_CONTRACT.md` 的契约规则）。
- **PM 的写入侧（riskbot）不在本仓库**：本仓库只有读取器与展示层，bundle 的字段语义以 riskbot 为准。
- **`account_view()` 已有第二个消费者**：`packages/decisions/redaction.py` 的 `redact_account_view`（输出 schema `puregamma.pm_judgment_state.v1`）在把数据交给第三方模型之前按**字段级 allowlist** 投影，与本模块"整体放行"的策略相反——契约上它默认丢弃 riskbot 将来新增的字段。
- **读取器与授权判定本身没有自动化测试**：`tests/` 下没有覆盖 `pm_riskbot_service` 读取分支或 `/portfolio/pm` 授权判定的用例；`tests/test_mobile_access_handoff.py`（在 `deploy/pm-paths.txt` 清单内）验证的是移动端会话交接，与 PM 数据无关。`tests/unit/test_pm_redaction.py` 覆盖的是上面那条 redaction 边界（以 `account_view()` 载荷为夹具），属于下游消费者测试。
- **`snapshot.age_seconds` 与 `captured_at_ms` 兜底分支在当前路径下不可达**：所有成功的 `BundleRead` 都带 mtime，`_age_seconds` 的第二个分支只作为防御性兜底存在。

> **English summary** — Known boundaries: only the top-level `schema` is validated (inner bags are pass-through, so absent vs. empty is indistinguishable), the bundle's producer (riskbot) lives outside this repo, there are no automated PM tests in this repo, and the `captured_at_ms` fallback in `_age_seconds` is currently unreachable.
