# P1 · 实盘与账务可审计（不开启实盘）

状态：代码与测试已完成。**没有执行任何生产部署、生产数据库迁移或切流，也没有开启 LIVE 实盘。** 新能力全部默认关闭，或者本身只读、只追加。
分支：`upgrade/live-ledger-audit`，基于 `main@0dfad2c`（v0.3.3）。

| 阶段 | 提交 | 内容 |
| --- | --- | --- |
| 1 | `68833f7`、`936870e` | 用户侧 Ledger 只读接口 + 对账视图，接入 Account 页 |
| 2 | `0ed9dd8` | UNKNOWN 订单的同步状态 + 只查询的“请求重新核对” |
| 3 | `f0662f2` | 管理端审阅：Kill Switch、LIVE 资格、对账异常、管理审计 |
| 4 | `5c7956b` | Mandate 提案 → 双人审批 → 生效（开关关闭，迁移 0036 只增不改） |
| 5 | `797748d`、`de2d13b` 及之后 | 重放/竞态/Postgres 测试，以及测试发现的缺陷修复 |

每个阶段都是独立提交，可以单独 `git revert`（阶段 5 的修复依赖阶段 2 的 `sync_order_status` 改动，回退阶段 2 时需要连同阶段 5 一起回退）。

---

## 1. 设计

### 1.1 用户侧 Ledger 与对账（阶段 1）

- `GET /api/trading/ledger`（`packages/live_trading/ledger_view.py`）：
  - 先按当前用户解析账户（可选 mandate），解析不到就抛 `LookupError` → **404**。他人的 id 与不存在的 id 返回完全相同的响应体，因此无法枚举；
  - SQL 同时按 `account_id` 和 `user_id` 过滤（纵深防御）；
  - 分页方式：按 `(created_at DESC, id DESC)` 做 keyset 分页。时间戳相同时靠 id 决定顺序；每页取 `limit+1` 条来判断是否还有下一页，返回 `next_cursor`，默认 50 条，上限 200 条（超出返回 422）；
  - 游标是不透明的 base64url JSON，带版本号，不携带任何权限：每一页都会重新执行所有权过滤，畸形游标返回 400 `INVALID_CURSOR`；
  - 新写入的行只会出现在第一页之前，不会让后续页错位（有测试）。
- `GET /api/trading/reconciliation`：
  - 按币种分别汇总 Ledger 推导的余额，不把 BTC 手续费和 USD 现金加在一起（现有 `cash_balance` 会跨币种求和，本次未修改，见遗留项）；
  - 返回 Ledger 推导的持仓，以及最近一次对账和最近 10 次的历史。
- 金额一律通过 `decimal_text` 输出为十进制字符串。对账 JSON 里用 `str(Decimal)` 写入的 `0E-8` 也会统一改写为普通十进制。
- “缺失”和“0”严格区分：
  - 没有记录的 `balance_after` 返回 `null`，界面显示“未记录”；
  - 没有账户时返回 404 `TRADING_ACCOUNT_NOT_FOUND`，界面显示“Ledger 不可用（不是零）”；
  - 有账户但没有任何行时，返回 `empty: true`、`balances: []`；
  - 从未对账时 `latest: null`，界面显示“比较结果不可用”，不会显示成“无差异”。
- Account 页（`live-trading-console.tsx` 的 `LedgerSection` / `ReconciliationSection`）替换了原来的“ledger 不可用”占位：
  - 读取失败时显示“暂时无法读取（不是空、不是零）”，并提供重试；
  - “加载更早记录”失败时保留已显示的行。

### 1.2 UNKNOWN 订单的同步状态（阶段 2）

- `control_plane.sync_order_status` 仍然**只调用 `gateway.query_order`**。每次查询结果分为三类，追加写入 `TradingAuditLog`（action `LIVE_ORDER_SYNC`，key 为 `audit:sync:<order>:<nonce>`）：
  - `resolved`：交易所给出了明确状态；
  - `still_unknown`：交易所有回应，但没有明确状态；
  - `query_failed`：查询本身失败，附原因。
- 后台任务（每 8 s）只在结果与上一次不同时才写一行，避免每单每天上万行。`live_orders.last_sync_at` 记录最近一次查询时间。**这个后台行为不受开关控制**（见 §3）。
- `GET /api/trading/orders/{id}/sync-status` 返回：最近查询时间、最近结果、最近 10 条历史，以及是否允许重新核对（`disabled` / `terminal` / `rate_limited`）。
- `POST /api/trading/orders/{id}/recheck`（`packages/live_trading/order_sync.py`），处理顺序如下：
  1. 开关关闭 → 403；
  2. 所有权：不是自己的订单 → 404；
  3. 已终结的订单 → 409；
  4. 对订单行 `FOR UPDATE` 加锁，检查本单最近一条 `LIVE_ORDER_RECHECK_REQUESTED` 审计行是否在最小间隔内 → 是则 429，带 `Retry-After`；
  5. 写入请求审计行并**先提交**（占住限流窗口），再调用 `sync_order_status`。
- 重新核对**不会**调用 `submit_order` / `cancel_order`，也不会新建 intent 或订单。Kill Switch 启用时同样允许，因为它只是查询。
- **不改表结构**：全部复用 `trading_audit_logs` 和 `live_orders.last_sync_at`。

### 1.3 管理端审阅（阶段 3）

- `packages/live_trading/admin_review.py` 加上 `/admin/trading/*` 路由，全部依赖服务端的 `admin_user`（`require_admin`，即 role == admin）。前端 `AdminGate` 隐藏页面只是为了体验，不起授权作用。
- Kill Switch：
  - 启用和释放都必须填写原因，并写入审计 `LIVE_KILL_SWITCH_ENGAGED/RELEASED`（记录管理员、原因、trace）；
  - 校验目标：global 不能带 `scope_id`；user/mandate/connection 必须带 `scope_id`，且对象必须存在，否则 400/404；
  - 释放一个并未启用的开关返回 404（修复：`kill_switch.release` 原来只要同 scope 下有任意启用中的开关就返回成功）；
  - 释放 mandate 级开关**不会**恢复被暂停的 Mandate，恢复仍需所有者输入确认短语，并重新通过全部门禁。
- LIVE 资格：
  - 必须填写原因（`notes` 由可选改为必填）；
  - **管理员不能批准自己的 LIVE 资格**；
  - 名义上限必须是非负十进制数；
  - 写入审计 `LIVE_USER_APPROVAL_SET`，记录变更前的状态。
- 对账异常：
  - 可按 `exceptions_only` / `unreviewed_only` / `status` 过滤，差异以只读方式展示；
  - “标记已审阅”必须填写备注，只追加一条 `LIVE_RECONCILIATION_REVIEWED` 审计行。`trading_reconciliations` 由模型事件保证不可改写，本次也不会修改 Ledger 或恢复 Mandate；
  - 用户侧只能看到“已审阅”和时间，看不到管理员身份和备注。
- 管理审计：`GET /admin/trading/audit`。
- 新页面 `/admin/trading`（`components/admin-live-trading-console.tsx`）：每项操作都会写明影响，并要求原因和手动输入确认短语（如 `ENGAGE global`、`APPROVE <user>`、`REVIEWED <id 前 8 位>`）。服务端返回 403 时显示“服务器拒绝”，不会显示成空列表。该页面已加入 `route-audit` 的路由表。

### 1.4 Mandate 创建与变更（阶段 4）

**现状评估**：在本次之前，产品里没有任何创建或修改 LIVE mandate 的入口（无用户 API，也无管理 API）。`TradingMandate` 行只能由运维直接写入，修改也没有双人复核。

**设计**（`packages/live_trading/mandate_proposals.py`，开关 `LIVE_MANDATE_PROPOSALS_ENABLED`，默认关闭）：

```
pending ──approve(管理员 #1)──▶ pending[1/2] ──approve(管理员 #2)──▶ applied
   │                                 │
   ├──reject(管理员, 原因)──▶ rejected   ├──（同左）
   ├──revoke(提案人/所有者/管理员, 原因)──▶ revoked
   └──超过 expires_at（默认 72h；任何读写时检查）──▶ expired
```

- 提案人：mandate 所有者可以为自己提案（`POST /api/trading/mandate-proposals`），管理员可以为任何用户提案（`POST /admin/trading/mandate-proposals`）。
- 审批人只能是管理员，且不能是提案人或 mandate 所有者；两次批准必须来自**两个不同的人**。批准操作在提案行 `FOR UPDATE` 锁内完成。新建 mandate 的 `idempotency_key = mandate:proposal:<id>` 唯一，因此并发的第二次批准也只会产生一个 mandate（Postgres 测试）。
- 条款校验在提案时和生效时各做一次：
  - 账户、strategy release（必须已批准）、券商连接都必须属于所有者；
  - 十进制限额必须满足 `per-order ≤ position ≤ total`、`daily_loss ≤ total`；
  - 杠杆必须为 1（只做现货），方向不能做空；
  - 交易标的必须在部署白名单内；
  - `max_total_notional` 不得超过所有者已批准的 LIVE 上限（生效时检查）。
- 与 Kill Switch 的关系：全局、用户或目标 mandate 的 Kill Switch 启用时，第二次批准会被拒绝（409），提案保持 pending，直到开关释放或提案过期。
- 与风控和静态门禁的关系：生效**不等于可以交易**：
  - 新建的 mandate 以 `paused=True` 开始，`pause_reason=dual_approval_applied: owner must resume`。所有者用 `RESUME <id>` 恢复时，`resume_mandate` 会重新评估完整门禁；
  - 每一笔订单仍然要经过 `flags.evaluate_full_gate`（部署级 `LIVE_TRADING_ENABLED` 等）和风控引擎；
  - 本模块不读取、也不修改任何 `LIVE_TRADING_*` 设置。测试证明静态门禁关闭时，已生效的 mandate 仍被拒绝。
- 修改（amend）：提案时记录 `base_revision`，生效时如果 mandate 的 `revision` 已经变化就拒绝（409，需要重新提案）。修改成功后 `revision+1`，并把审批人写进 `audit_metadata_json.amendments`。目标 mandate 自身的 Kill Switch 启用时拒绝修改。
- 审计：每一次转移都写 `LIVE_MANDATE_PROPOSED / _APPROVED / _REJECTED / _REVOKED / _EXPIRED`，记录操作人、原因或备注、第几次批准。
- 存储：新表 `trading_mandate_proposals`，见迁移 `packages/database/alembic/versions/0036_trading_mandate_proposals.py`，**只新增表，不改动已有表**。
  - **需要随部署执行迁移，本次没有在任何生产库上执行**；
  - 开关关闭（默认）时，所有提案路由返回 404，其他代码路径都不读写这张表。有测试证明：删除这张表后，下单、同步、撤单、暂停、Ledger、对账、管理端各条路径都能正常工作；
  - 开关开启但迁移尚未执行时，返回 503 `MANDATE_PROPOSALS_UNAVAILABLE`，不会出现 500。
- 本次没有做提案的前端界面（见遗留项）。

### 1.5 测试中发现并修复的缺陷（阶段 5）

| 缺陷 | 影响 | 修复 | 证明 |
| --- | --- | --- | --- |
| 暂停/恢复的审计键为 `audit:pause:<id>:<unix 秒>` | 同一秒内的第二次转移被 `audit()` 当作重复而**静默丢弃审计行** | 改为每次转移使用一个 nonce | Postgres 交替不变量测试（PAUSE/RESUME 必须交替，最终状态与最后一条审计一致）；SQLite 同秒测试。改回旧键后两者都失败 |
| 撤单审计键为 `audit:cancel:<order>` | 失败后重试撤单，重试那次**没有审计** | 每次尝试一个 nonce，并在结果中记录 `error_code`；成功后清除过期的 `CANCEL_UNKNOWN` | `test_a_retried_cancel_is_audited_and_clears_its_failure` |
| `confirm_order` 拿到 mandate 锁之后没有重新检查 | 并发确认同一 intent 时，输掉的一方会重新跑风控；如果风控拒绝，会把**已批准的 intent 改成 REJECTED** | 拿到锁后先 `refresh(intent)`，如果已有订单就直接返回 | `test_a_confirm_that_loses_the_race_returns_the_winners_order`（在拿锁时注入胜者的写入） |
| 撤单返回 200 + `CANCEL_UNKNOWN` 时界面仍显示“已撤单” | 用户以为已经撤掉 | 界面显示“交易所没有确认撤单，未重发” | E2E `live-trading-recheck` |
| `kill_switch.release` 只要同 scope 下有其他启用中的开关就返回成功 | 释放时写错 id 也显示成功 | 只统计 `scope_id` 完全匹配的开关 | `test_releasing_a_switch_that_is_not_active_is_a_404` |

另外：去掉 `confirm_order` 的 mandate 行锁后，唯一键 `uq_live_order_idempotency` 仍然能保证最多只有一单，但并发中输掉的请求会因 `IntegrityError` 失败（3 次运行中出现 1 次）。也就是说，唯一键负责保证“一单”，行锁负责让输掉的一方干净地返回同一单。

## 2. 威胁模型

| 威胁 | 对策 | 证据 |
| --- | --- | --- |
| 用户 A 读取或枚举 B 的 ledger/对账/订单同步 | 先按所有权解析，他人与不存在一律 404 且响应体相同；SQL 双重过滤；游标不携带权限 | `test_live_trading_ledger_view.py`、`test_live_trading_order_recheck.py`；变异测试 |
| 篡改游标越权或注入 | 游标只包含 `(时间, id)` 位置，每页都重新做所有权过滤；畸形游标返回 400 | `test_a_cursor_carries_no_authority`、`test_a_malformed_cursor_is_a_400_not_a_500` |
| “重新核对”被用来重下单或刷交易所 | 代码路径只到 `query_order`；每单在行锁下限流；开关默认关闭 | spy gateway 断言 `submit/cancel` 从未被调用；PG 并发 5 次请求只查询 1 次；变异：混入 submit 后 6 项失败 |
| 非管理员调用管理 API（前端隐藏被绕过） | 服务端 `admin_user` 依赖 | 8 条路由 × 普通用户 403、匿名 401；变异：去掉依赖后测试失败 |
| 管理员自批（LIVE 资格 / mandate） | 服务端拒绝 | 测试 + 变异测试 |
| 单人生效 mandate | 两名不同的管理员，且都不是提案人或所有者 | 测试 + 变异测试；PG 并发批准只生成 1 个 mandate |
| mandate 生效即开始交易，或绕过静态门禁 | 生效后处于暂停状态；订单仍经过完整门禁 | `test_two_different_admins_make_it_effective_but_paused_and_still_gated` |
| 并发确认重复下单 | 唯一键 + mandate 行锁 + 锁内重新检查 | PG 6 线程只提交 1 次；SQLite 注入竞态 |
| Kill Switch 吞掉撤单 | 撤单路径不检查 Kill Switch；每次撤单都有审计 | SQLite 4 个 scope；PG 启用与撤单并发 |
| 审计丢失 | 每次转移、每次尝试都有唯一键 | 见 §1.5 |
| 把缺失数据显示为 0 | `null` / `empty` / 404 三者分开，界面文案分开 | 单元测试 + E2E |

## 3. 开关（全部默认值）

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `LIVE_ORDER_RECHECK_ENABLED` | `false` | 用户按需重新核对；关闭时 POST 返回 403，界面不显示按钮，并说明“服务器仍在后台查询” |
| `LIVE_ORDER_RECHECK_MIN_INTERVAL_SECONDS` | `60`（下限 10） | 每单的重新核对间隔 |
| `LIVE_MANDATE_PROPOSALS_ENABLED` | `false` | 提案流程；关闭时所有提案路由返回 404 |
| `LIVE_MANDATE_PROPOSAL_TTL_HOURS` | `72` | 提案过期时间 |
| 现有 `LIVE_TRADING_ENABLED` 等 | 不变（false） | 本次没有改动，也没有读取或修改这些门禁 |

**不受开关控制、但属于只读或只追加的变化**（需要知晓）：

- `GET /api/trading/ledger`、`/reconciliation`、`/orders/{id}/sync-status`：只读、按所有者校验。没有 LIVE 账户的用户只会得到 404。
- 后台 `sync_order_status` 在结果变化时追加 `LIVE_ORDER_SYNC` 审计行：
  - 它与订单状态更新在**同一事务**内；
  - 如果审计写入失败，整个同步（状态、fill、ledger）一起回滚。`sync_live_order_statuses` 会按订单 rollback 并记录日志，8 s 后的下一轮会重新查询。效果与“交易所这一轮没有回应”相同，绝不会重新下单（`test_a_failed_audit_write_rolls_the_whole_sync_back_and_the_next_tick_retries`）。
  - 选择同一事务，是为了避免出现“状态已变但没有审计”的情况。
- 管理端变化：
  - 新增 GET 接口和审阅 POST 接口；
  - `POST /admin/trading/live-approvals` 的 `notes` 改为必填；
  - `POST /admin/trading/kill-switch` 增加目标校验，释放不存在的开关返回 404，并写入审计；
  - 管理员不能批准自己的 LIVE 资格。
  - 仓库内没有其他调用方（已 grep 确认）；如果外部有脚本调用，需要补上原因。

## 4. 测试证据（本机实测，2026-10-29）

环境：共享 venv `/var/tmp/pgvenv`（Python 3.12）。Postgres 是一次性容器 `pgws-w2-pg`（`postgres:17`，`127.0.0.1:55432`，`fsync=off`，测试结束后删除）。重任务都在 `flock … systemd-run --user --scope -p MemoryMax=2000M` 中执行。

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| 新增后端测试 | `pytest tests/security/test_live_trading_{ledger_view,order_recheck,admin_review,mandate_proposals,races}.py` | 见 §4.1 |
| Postgres | `PUREGAMMA_TEST_POSTGRES_DSN=postgresql+psycopg://postgres:***@127.0.0.1:55432/pgws pytest tests/security/test_live_trading_ledger_postgres.py tests/security/test_live_trading_concurrency_postgres.py` | 7 通过、0 跳过；连续 5 次稳定通过（不设 DSN 时这 7 项跳过） |
| 后端全量 | 见 §4.1 | 见 §4.1 |
| ruff（CI 规则） | `ruff check apps packages services scripts tests --select E9,F63,F7,F82` | 通过 |
| Web | `pnpm --dir apps/web typecheck`、`lint` | 通过；lint 只有已有的警告，新文件没有警告 |
| Playwright（chromium + mobile-chrome，`--workers=1`，每个 spec 单独起一个 `next dev`） | `live-trading-ledger` 12、`live-trading-recheck` 10、`live-trading-admin` 16、`live-trading` 10、`live-trading-workflow` 24、`admin-console` 12、`admin` 4×2、`route-audit --grep /admin/trading` 2 | 见 §4.1 |

### 4.1 汇总

| 范围 | 结果 |
| --- | --- |
| 新增后端测试 | ledger_view 19、order_recheck 13、admin_review 28、mandate_proposals 23、races 6，全部通过（不需要 Postgres） |
| Postgres（`postgres:17` 一次性容器） | `test_live_trading_ledger_postgres.py` 3 项（含 23 行、其中 17 行 created_at 完全相同的 keyset 翻页，每页 1/4/5/17/22 条，不重不漏）+ `test_live_trading_concurrency_postgres.py` 5 项：**8 通过、0 跳过**，连续多次稳定通过。不设 DSN 时这 8 项按设计跳过 |
| 后端全量 `pytest tests`（heavy flock + 2000M scope，不设 DSN） | **1377 通过、8 跳过、4 xfailed、0 失败**。第一次运行时 `tests/unit/test_pocket_relay.py` 有 5 个 error，原因是共享 venv 缺少 `qrcode`（CI 会从 `apps/pocket-relay/requirements.txt` 安装），补装后这 5 项通过 |
| ruff（CI 规则） | All checks passed |
| `pnpm typecheck` | 通过 |
| `pnpm lint` | rc=0，9 个警告，均为已有文件中的已有警告（与 v0.3.3 基线的 9 个相同），新文件没有警告 |
| Playwright（`next dev`，chromium + mobile-chrome） | live-trading-ledger 12/12、live-trading-recheck 10/10、live-trading-admin 16/16、live-trading 10/10、live-trading-workflow 24/24、admin 8/8、route-audit `/admin/trading` 2/2 |
| Playwright（生产构建 `next build` + `next start`，与 CI route-audit 相同的环境变量） | **route-audit 全量 116/116**（新增 `/admin/trading` 后由 114 增至 116）、admin-console 12/12、live-trading-admin 16/16、live-trading-workflow 24/24、live-trading-ledger 12/12、live-trading-recheck 10/10。`live-trading.spec` 在生产构建下有 4 项失败：这 4 项读取的是仅在 `NODE_ENV=development` 下存在的诊断钩子（`plugins/core/runtime.tsx`），与本次改动无关，在 `next dev` 下 10/10 通过 |

说明：`admin-console.spec` 在 `next dev` 下编译 `/admin` 时，内存超过 2000M scope 上限，在 cgroup 内被 OOM 杀掉（没有波及其他进程）。因此按协调者的要求改用生产构建运行并通过。

### 4.2 变异测试（去掉关键守卫后相应测试失败）

| 守卫 | 变异 | 结果 |
| --- | --- | --- |
| Ledger 账户所有权 | 去掉 `TradingAccount.user_id` 过滤 | 4 项失败 |
| Ledger mandate 所有权 | 去掉 mandate 的 user/account 过滤 | 1 项失败 |
| Keyset 平局 | 游标条件去掉 `id` 平局分支 | Postgres 平局翻页测试失败 |
| 重新核对的所有权 | 去掉 `LiveOrder.user_id` 过滤 | 1 项失败 |
| 重新核对限流 | 跳过限流检查 | 1 项失败 |
| 只读保证 | `sync_order_status` 中先调用 `submit_order` | 6 项失败 |
| 管理端授权 | kill-switch 路由改用 `get_current_user` | 1 项失败 |
| 自批 LIVE 资格 | 去掉检查 | 1 项失败 |
| 释放不存在的开关 | 视为成功 | 1 项失败 |
| 提案：提案人自批 / 同一人两次批准 / 过期 / Kill Switch / 生效后不暂停 / 忽略开关 | 分别去掉 | 各 1 项失败 |
| 审计键（暂停） | 改回每秒一个键 | SQLite 1 项失败，PG 1 项失败 |
| 审计键（撤单）、锁内重新检查、`CANCEL_UNKNOWN` 清除 | 分别改回 | SQLite 各 1 项失败 |
| `confirm_order` 的 mandate 行锁 | `lock=False` | PG 并发重放测试 3 次中 1 次失败（IntegrityError），唯一键仍保证只有一单 |

## 5. 回滚

- 代码：按阶段 `git revert`，顺序为 5 → 4 → 3 → 2 → 1。
- 数据库：
  - 阶段 1–3 和 5 **没有改动表结构**，只多了若干审计行，旧代码会忽略它们；
  - 阶段 4 的迁移 0036 只新增表，`downgrade()` 会删除表和索引。回滚代码时可以保留这张表（旧代码不引用它），也可以执行 downgrade；
  - 如果已经有 `applied` 的提案，它创建的 `trading_mandates` 行属于正常的 mandate，回滚代码不影响这些行。
- 开关：
  - 把 `LIVE_ORDER_RECHECK_ENABLED` 和 `LIVE_MANDATE_PROPOSALS_ENABLED` 设回 `false` 即可立即关闭对应的写操作入口；
  - 后台同步的审计写入无法通过开关关闭，需要回退阶段 2 的提交。
- 管理 API 的兼容性：回退阶段 3 后，`notes` 恢复为可选，释放不存在的开关恢复为 200（原有缺陷）。

## 6. 遗留项

- Mandate 提案没有前端界面（只有 API）。如需界面，应放到管理端审阅页，并按“领域视图由 Harness 插件拥有”的原则评估是否改做成插件。
- `ledger.cash_balance` 会跨币种求和（BTC 手续费会被当作 USD 扣减）。它被风控和对账使用；修改会影响风控语义，本次只在用户视图中改为按币种汇总。建议单独立项。
- `pause_mandate` / `resume_mandate` 在无操作分支（已暂停 / 未暂停）直接返回，没有结束事务，在请求结束前会一直持有行锁。HTTP 下请求结束就释放；后台调用方需要注意。
- `sync_order_status` 在订单从 `UNKNOWN` 恢复后保留 `error_code=SUBMIT_UNKNOWN`（作为历史保留），界面上依靠同步状态说明。是否清除需要产品决定。
- 管理端 `GET /admin/trading/ledger` 仍用 `str(Decimal)` 输出（可能出现 `0E-8`），未改动。
- `route-audit` 只针对新路由在 `next dev` 下跑过（2/2）。全路由的生产构建审计由协调者在合并时执行。
- 管理端变更（`notes` 必填、释放 404）如果有仓库外的脚本调用，需要随部署告知运维。

### 需要用户拍板的事项

- 是否以及何时在生产执行迁移 0036，并开启 `LIVE_MANDATE_PROPOSALS_ENABLED`（以及审批人名单：目前是“任意两个不同的管理员”）。
- 是否开启 `LIVE_ORDER_RECHECK_ENABLED`，以及限流间隔（默认 60 s）。
- 后台同步审计行的保留策略（目前只追加，没有清理）。
- 通用事项（不属于本主题，沿用协调者列表）：`AGENT_MODEL_CREDIT_RATES` 费率、生产部署时间、staging 环境与真实 key、测试账号、GitHub 默认分支改为 main、claude.ai 连接器授权。

## 7. 交接

- 已完成：阶段 1–5 全部完成并推送；文档、`docs/live-trading/FEATURE_FLAGS.md` 和 `API.md` 已更新。
- 进行中：无。
- 下一步（建议）：
  - Mandate 提案的管理端界面；
  - `ledger.cash_balance` 按币种拆分（需单独评审风控语义）；
  - 协调者合并前在 CI 上跑全量 Playwright 分片和 commercial gates。
- 已验证的命令：
  - `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /var/tmp/pgvenv/bin/python -m pytest -o addopts=--import-mode=importlib -q tests`（套 heavy flock 与 `systemd-run --user --scope -p MemoryMax=2000M`）；
  - `PUREGAMMA_TEST_POSTGRES_DSN=postgresql+psycopg://postgres:<pw>@127.0.0.1:55432/pgws … pytest tests/security/test_live_trading_ledger_postgres.py tests/security/test_live_trading_concurrency_postgres.py`；
  - Playwright：每个 spec 单独起一个 `next dev`（端口 3150，SSR fixture 端口 3151，`--workers=1`）；或者在 `NEXT_DIST_DIR=.next-playwright` 下 `next build` 后用 `next start` 运行。
