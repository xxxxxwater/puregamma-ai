# 移动端与 API 契约对齐（W3，2026-10-29）

分支 `upgrade/mobile-contract-align`（起点 `origin/main` `0dfad2c`，v0.3.3）。范围：iOS（SwiftUI）与 Android（Compose）对齐 `main` 上已经上线的
Agent 会话、实盘 NAV 与错误码契约；补齐契约文档、服务端契约测试与共享样例；移动端单元测试第一次进入 CI。

不改服务端行为，不改发布工作流的语义，不新增 feature flag（见"开关"）。

## 1. 现状与问题（`main` 实测）

| 契约项 | 服务端（已上线） | iOS 1.5.0 | Android 1.5.0 |
|---|---|---|---|
| (a) 幂等发送 | `client_request_id` + 409 `DUPLICATE_SUBMISSION{runId,…}` | 不带 id；"重试"重新 POST（可能二次扣费）；SSE 错误体被丢弃（`validate(…, data: Data())`），409 只剩状态码 | 不带 id；`SseClient` 抛错时丢失 `code` |
| (b) 权限模式 | 只能选 `read-only`/`workspace-write`；`full-access` 400/降级；运行中 409 | 无权限设置 | 无权限设置 |
| (c) NAV 无账户 | 404 `TRADING_ACCOUNT_NOT_FOUND` | 不调用 `/api/portfolio/nav` | 不调用 |
| (d) 已删除会话 | 404 纯字符串 | 落到通用 `.server` | 通用错误 |
| (e) 金额 | 实盘接口十进制字符串 | `Decimal` 只收数字，字符串解码失败 | `Double` |
| (f) 模型目录 | `reason`/`category`/`estimate`，`jev` 是 `evaluation` | 列出全部模型（含 jev），原样显示 `reason` 代码 | `models.take(4)`，不看 category |
| (g) 事件回放 | `/runs/{id}/events?after=`、`active_run_id`、每帧 `seq`/`at` | **未知事件抛错中断流**；无回放；进入后台会**取消** run | 未处理 `run.canceled`；无回放 |
| 测试 | — | Swift Testing 11 个文件，**CI 从不运行** | JUnit 9 个文件，只在发布工作流里跑 |

另外发现：SQLite（以及部分存储路径）返回不带时区偏移的时间戳，iOS 的日期解码会让整条响应失败；Android 会退化为 1970-01-01。

## 2. 设计

### 2.1 契约文档 + 共享样例 + 服务端契约测试

- `docs/mobile/MOBILE_API_CONTRACT.md`：修正过期头部与 §6 实现状态（research/memory/mandate 已上线；mandate 的 `status/risk/preview` 子资源仍未实现），新增 §8（(a)–(g) 逐项：请求/响应 JSON、状态码、错误码、客户端行为）、§9 错误码表、§10 客户端版本表。
- `tests/contract/test_mobile_agent_contract.py`（27 个用例）：TestClient 打真实路由，断言状态码/错误码/字段集合，并把响应写成 `docs/mobile/fixtures/*.json|.sse`。
  每次运行都会变化的值（UUID、时间、`latencyMs`）按出现顺序替换成稳定值（同一个值始终映射到同一个替身，保持交叉引用）。
  测试把实时响应与已提交样例**逐字节比较**：服务端改了形状而没有更新样例，测试就失败（`PG_WRITE_MOBILE_FIXTURES=1` 重新生成，变更需要审阅）。
- iOS 用 `#filePath` 定位样例，Android 由 Gradle 通过系统属性 `pg.contractFixtures` 传入路径——两端解码的是同一份文件。

### 2.2 客户端（两端同构）

| 职责 | iOS | Android |
|---|---|---|
| 请求 id | `ClientRequestID.make()` → `ios-<uuid>` | `ClientRequestId.make()` → `android-<uuid>` |
| 一次发起 | `AgentSendAttempt{content, context, requestID, accepted}` | `AgentSendAttempt{content, model, requestId, accepted}` |
| 失败分类 | `AgentSendFailure.classify`：`duplicate(runId)` / `conversationGone` / `retryable` / `final` | 同名 sealed interface |
| 错误信封 | `APIErrorDetail{status, code, message, fields}`，`APIError.rejected`（所有 404/409；发送流上所有带 code 的拒绝） | `ApiErrorDetail`，`RetrofitApiException.detail`；`apiCall{}` 把 Retrofit `HttpException` 连同错误体转换 |
| 帧 | `AgentStreamFrame{name, seq, runID, event}`，未知类型 → `.ignored` | `AgentFrame`，未知类型 → `Ignored` |
| 去重 | `AgentRunCursor.admit`：`seq <= lastSeq` 丢弃；`runId` 不是当前 run 丢弃 | `AgentRunCursor` 同规则 |
| 回放 | `AgentRunFollower.follow`：网络错误等待重试；404 停止；终态返回 | `AgentRunFollower` 同规则 |
| 一个回合 | `AgentViewModel.submit` | `AgentTurnRunner.run`（纯逻辑，`AppViewModel` 只负责状态） |
| 模型菜单 | `AgentModelMenu.entries/resolve` | 同名 |
| 权限模式 | `AgentPermissionMode.selectable(from:)` | `AgentPermissionMode.selectable` |
| NAV | `LiveNavRepository` → `LiveNavState.noAccount/loaded` | 同名 |
| 十进制 | `LenientDecimal`（字符串或数字 → `Decimal`） | DTO 用 `String` 承载（Gson 把数字按字面量读入 String），`decimalOrNull` → `BigDecimal` |

回合语义（与 Web `agent-chat.tsx` 一致）：

1. 用户发起 → 新 id；乐观插入用户消息与占位回答。
2. 服务端以 200 接受（`accepted = true`）之前的任何失败：`retryable` 保留这次发起，"重试"**用同一个 id**；服务端其实收到了的话会返回 409，客户端随即附着原 run——不会二次扣费。
3. 409 `DUPLICATE_SUBMISSION`：移除乐观消息，按 `runId` 跟随事件日志（原 run 已是终态则直接重新拉取会话）。
4. 流在终态帧之前结束或断开：显示"连接中断，正在从服务端恢复"，从 `lastSeq` 继续回放；`runId` 未知时用会话快照的 `active_run_id`。网络错误只等待，不判失败。
5. 终态后重新拉取会话，以服务端记录覆盖本地流式内容。
6. 打开会话 / 回到前台：快照有 `active_run_id` 就附着观察。
7. 进入后台、切换会话：只停止观察（iOS 不再调用取消）；取消只由"停止"按钮触发。
8. 404 `Conversation not found`：从列表移除、清空视图、提示"该会话已被删除"。

### 2.3 CI

新工作流 `.github/workflows/mobile-tests.yml`（不改 `mobile-release.yml`）：推送到 `main` 或 `upgrade/**`，且改动 `apps/android/**`、`apps/ios/**`、`docs/mobile/**`、`tests/contract/**`、相关服务端文件或工作流本身时运行：

- `contract`：Python 3.12，`pytest tests/contract` + `git diff --exit-code docs/mobile/fixtures`。
- `android`：JDK 17，`./gradlew :app:testDebugUnitTest`，汇总测试数写入 step summary，上传报告。
- `ios`：macos-15（Xcode 16.4），自动挑选可用 iPhone 模拟器，`xcodebuild test -only-testing:PureGammaTests`，`SWIFT_VERSION=5.0`（与发布构建一致），**ad-hoc 签名**（`CODE_SIGN_IDENTITY=-`）——`CODE_SIGNING_ALLOWED=NO` 时模拟器 App 没有钥匙串访问组，既有的 Keychain 测试会以 `errSecMissingEntitlement (-34018)` 失败；汇总 `xcresult` 测试数。
- `concurrency.cancel-in-progress: false`：连续推送时排队而不是取消，保证每个 head 都有完整结果。

## 3. 威胁模型

| 威胁 | 处理 |
|---|---|
| 重放/重复提交导致二次扣费 | 服务端在会话行锁下按 `client_request_id` 去重（24 h）；客户端在未被接受前重试复用同一个 id，409 附着原 run，不重发 |
| 伪造/猜测他人 `runId` 读取事件 | 服务端按 owner 校验，他人 run 一律 404（契约测试 `test_replay_of_someone_elses_run_is_404`）；客户端遇到 404 停止跟随，不重试 |
| 他人 run 的帧混入当前会话 | `AgentRunCursor` 丢弃 `runId` 不匹配的帧 |
| 重复投递导致内容重复 | 按 `seq` 去重 |
| 通过发送 payload 提升权限 | 服务端忽略 payload 中的 `permission_mode`（契约测试 `test_the_send_payload_cannot_raise_the_permission_mode`）；客户端不提供 `full-access` |
| 未定价模型被计价 / 显示编造价格 | 菜单只允许 `available && category == generation`；不可用模型置灰并显示原因；客户端从不自行估价 |
| 无账户时显示 0 误导用户 | NAV 404 → 空状态；`nav == null` → "不可用"；NAV 不缓存 |
| 浮点误差进入金额 | 十进制类型端到端；图表只在绘制几何时转 `Double` |
| 错误信息泄露 | 客户端日志只记录状态码与错误码；凭证仍只在 Keychain/Keystore；错误体读取上限 64 KB |
| 后台断开被误判为失败 / 被误当成取消 | 断开只停止观察；回到前台按服务端记录恢复 |

## 4. 开关（全部默认值）

本次**没有新增开关**：客户端改动只消费服务端已上线、默认启用的行为（`client_request_id` 是可选字段，对 1.5.0 客户端向后兼容）。相关既有开关不变：

| 开关 | 默认 | 说明 |
|---|---|---|
| `APP_MIN_VERSION`（`apps/api/routers/mobile.py`） | `"1.5.0"` | 未改；是否强制升级到 1.6.0 由产品决定 |
| `harness_research_enabled` / `memory_service_enabled` / `auto_trading_*` | `false` | 未改 |
| `AGENT_MODEL_CREDIT_RATES` | 空（未定价模型不可用） | 未改；gpt-6 系列费率需用户拍板 |
| CI：`mobile-tests.yml` | 仅在相关路径变化时运行 | 不影响发布；`mobile-release.yml` 未改 |

## 5. 测试证据

### 5.1 本机

| 命令 | 结果 |
|---|---|
| `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /var/tmp/pgvenv/bin/python -m pytest -o addopts=--import-mode=importlib -q tests/contract` | 28 passed |
| 同上，连续 3 次，比较样例 | 每次逐字节一致（稳定） |
| 相关：`tests/contract tests/unit/test_agent_session_reliability.py tests/security/test_live_trading_nav_http.py tests/unit/test_agent_model_pricing.py`（合并 `origin/main` 之后） | 60 passed |
| 全量 pytest（flock + `systemd-run --scope MemoryMax=2000M`，`--ignore=tests/e2e`），合并前 | 1315 passed, 3 skipped, 4 xfailed（199 s） |
| 全量 pytest，合并 `origin/main`（`6d51452`）之后 | 1411 passed, 9 skipped, 4 xfailed（222 s） |
| `tests/contract`，再次合并 `origin/main`（`07d35f1`）之后 | 28 passed |
| `/data/home/.cache/ruffvenv/bin/ruff check apps packages services scripts tests --select E9,F63,F7,F82` | All checks passed |

本机没有 JDK/Android SDK，也不能编译 SwiftUI；下载工具链被沙箱策略拒绝，因此移动端只在 CI 上编译与测试。

### 5.2 CI（`Mobile Unit Tests`）

| 运行 | head | 结果 |
|---|---|---|
| [40867268134](https://github.com/xxxxxwater/puregamma-ai/actions/runs/40867268134)（基线，未改客户端） | `41cfade` | Android 57/57；iOS 72 个中 70 通过，2 个 Keychain 测试因 `CODE_SIGNING_ALLOWED=NO` 失败（-34018） |
| [40872124489](https://github.com/xxxxxwater/puregamma-ai/actions/runs/40872124489) | `517983d` | **全绿**：contract ✅，Android **81/81**，iOS **97/97** |
| [40873718689](https://github.com/xxxxxwater/puregamma-ai/actions/runs/40873718689)（合并 `origin/main` 后） | `6d51452` | **全绿**：contract ✅，Android **81/81**，iOS **97/97** |

测试数量变化：Android 57 → 81（+24），iOS 72 → 97（+25，基线的 2 个 Keychain 失败已修复）。

CI 首先暴露并修复了三个真实问题：

1. **iOS 从未解析过实时 SSE 帧**（既有缺陷）：`URLSession.AsyncBytes.lines` 不输出空行，而 `SSEParser` 只在空行时产出一帧，所以真实流上一帧都没有产出，界面只靠流结束后的重新拉取追上。现在帧在下一个 `event:` 行或流结束时也会结束（`SSEParserTests.framesSplitWithoutBlankLines`，研究任务事件流同样受益）。
2. `AGENT_MODEL_PRICING_NOT_CONFIGURED`（503）被"5xx 一律可重试"规则当成可重试；现在带错误码的拒绝只有并发/容量/模型暂不可用三类可重试（两端）。
3. Keychain 测试需要签名：改为模拟器 ad-hoc 签名。

### 5.3 变异测试

| 变异 | 结果 |
|---|---|
| 服务端：409 详情去掉 `runId`（`apps/api/routers/agent.py`） | `tests/contract` 1 failed（`test_a_resend_with_the_same_request_id_is_409_with_the_original_run`） |
| 服务端：NAV 无账户改回纯字符串 404 | `tests/contract` 3 failed（三个 `portfolio_*_no_account_404`） |
| 客户端 M1：未知帧不再忽略（当作失败）；M2：409 不再附着原 run（两端同时变异，分支 `upgrade/mobile-contract-align-mutation2` `7c2a907`，[40873625566](https://github.com/xxxxxwater/puregamma-ai/actions/runs/40873625566)） | iOS 97 个中 **4 个失败**：`unknownFramesAreIgnoredAndTheStreamContinues`、`anUnknownFrameDoesNotEndTheTurn`（M1），`duplicateSubmissionKeepsTheOriginalRun`、`aDuplicateSubmissionAttachesToTheOriginalRunInsteadOfResending`（M2）；Android 81 个中 **5 个失败**：`unknownFrameTypesAreIgnored`、`aCompleteStreamWithAnUnknownFrameEndsNormally`（M1），`duplicateSubmissionKeepsTheOriginalRun`、`aDuplicateSubmissionAttachesToTheOriginalRun`、`aDuplicateOfAFinishedRunJustReloads`（M2）。未变异的同一 head 全绿 |

变异分支只用于 CI 证据，不合并。

## 6. 回滚

- 每个阶段是独立提交，可单独 `git revert`：契约文档/测试/样例、iOS、Android、CI、升版。
- 回滚客户端不需要服务端配合：服务端行为没有改动，1.5.0 客户端仍被接受（`app_min_version` 未改）。
- 已发布的 1.6.0 客户端回滚 = 重新发布 1.5.x；服务端无需任何操作。
- CI 工作流删除即可，不影响 `mobile-release.yml`。

## 7. 遗留项与需要拍板的事项

遗留项：

- **后台继续生成**：服务端在 SSE 连接关闭时会把仍在进行的 run 结束为 `interrupted`（`_finalize_disconnected_run`）。客户端已改为"断开观察但不取消"，回到前台后如实显示 `interrupted` 与已生成的部分；真正在后台继续生成需要服务端把执行与连接解耦（DSH/Harness 会话路径），不在本任务范围。
- 移动端没有工具审批 UI：`approval.required` 只显示为活动提示，审批需在 Web 完成（或等待过期）。
- 旧 `GET /portfolio` 仍返回 float；两端已用十进制类型解码，但服务端精度在序列化时已经损失，需要服务端改为字符串（不在本任务范围）。
- `HARNESS_CORE_V2.md` 的 `dsh-mobile-api` / agent-chat 插件尚未挂载；本次的样例与契约测试可直接作为退役 FastAPI 路由时的对等性（parity）测试材料。
- iOS 的 `SWIFT_DEFAULT_ACTOR_ISOLATION` 只在 Xcode 26 生效，CI（Xcode 16.4）下被忽略；本次代码在两种设置下都不依赖默认隔离。

需要用户拍板：

- 是否把 `APP_MIN_VERSION` 提升到 `1.6.0`（强制升级）。
- 其余见协调者汇总：gpt-6-luna/sol/astra 费率、生产部署时间、staging 与真实模型 key、测试账号、GitHub 默认分支改为 `main`、claude.ai 连接器授权。

## 8. 交接

状态：全部 6 项完成（契约文档与契约测试、iOS、Android、断线恢复（随两端客户端提交）、测试与 CI、升版）。

| 提交 | 内容 |
|---|---|
| `41cfade` `70c3aa7` `fa15091` | CI 工作流（ad-hoc 签名、排队不取消） |
| `6d3344f` | 契约文档 §6/§8/§9/§10、契约测试、共享样例 |
| `f9b3c8f` `fa15091` `847e271` | iOS 适配与断线恢复；SSE 分帧修复；错误分类修复 |
| `d5d0aa9` `e697a0b` `ad789f1` `517983d` | Android 适配与断线恢复；编译修复；恢复 CRLF |
| `87fe5af` | 升版 iOS 1.6.0 (3) / Android 1.6.0 (10)，`APP_MIN_VERSION` 保持 1.5.0 |
| `6d51452` `07d35f1` | 合并 `origin/main` |

已验证命令见 §5。下一步（需要时）：

- 合入 `main` 后 `Mobile Unit Tests` 会在 `main` 上自动运行；发布仍按 `mobile-release.yml` 原流程。
- 变异分支 `upgrade/mobile-contract-align-mutation`、`upgrade/mobile-contract-align-mutation2` 只是 CI 证据，可删除。
- 修改 §8 涉及的服务端行为时：先改契约文档，`PG_WRITE_MOBILE_FIXTURES=1` 重新生成样例并审阅 diff，再同步两端 DTO 与测试。
