# 变更文件清单与验证结果（2026-08-15）

> 本文件包含两轮内容：首次实施 + 评审修复轮（见文末"评审修复轮变更"）。

## 0. 环境结论（评审要求，明确记录）

- **iOS**：已在本机 `xcodebuild build` + `xcodebuild test`（iPhone 17 Pro 模拟器）通过；但交付前仍应在当前工作区版本重新执行一次（已重新执行，见第 3 节）。
- **Android**：本机 macOS **无 JDK 17（按用户要求不安装）**，本次**未在本机完成 Gradle 构建/单元测试**，只做了 IDE 静态诊断（0 error）。最终构建与测试必须在 CI 或有 JDK 17 的专用环境完成：
  ```bash
  cd apps/android && ./gradlew :app:testDebugUnitTest
  ```
- **本机 macOS 不应修改生产 `.env`、服务器配置或数据库**；本分支未做任何此类修改。
- 工作区无关变更清理方案见 `GIT_HYGIENE.md`。

## 1. 变更文件清单

### 契约与文档（新增）

| 文件 | 说明 |
|---|---|
| `docs/mobile/MOBILE_API_CONTRACT.md` | 统一移动端 API 契约 v1（capabilities / research runs / memory / mandates / 推送深链），标注后端实现状态 |
| `docs/mobile/SECURITY_CHECKLIST.md` | 安全检查清单 |
| `docs/mobile/FEATURE_FLAGS_RELEASE_NOTES.md` | Feature Flag 发布说明 |
| `docs/mobile/ROLLBACK_PLAN.md` | 回滚方案 |
| `docs/mobile/CHANGELIST_AND_VERIFICATION.md` | 本文档 |

### iOS（`apps/ios/PureGamma`，SwiftUI 原生）

| 文件 | 类型 | 说明 |
|---|---|---|
| `Core/Models/MobileDomainModels.swift` | 新增 | `MobileCapabilities`、`ResearchRunState`（含 idle/submitting）、`ResearchVerification`、`ResearchRun`、`ResearchEvidence`、`MemoryState`、`MemoryScope`、`MemoryItemLifecycle`、`MemorySettings`、`MemoryItem`、`MemoryProposal`、`TradingEnvironment`、`TradingMandate`、`MandateRiskLimits`、`MandateStatus`、`MandateActionPolicy`（LIVE 恒不可操作） |
| `Core/Models/MobileAPIModels.swift` | 新增 | 全部 Codable DTO；capabilities 字段全部可选（缺失即 false）；`LenientDecimal` 兼容字符串/数字编码 |
| `Core/Persistence/MobileRepositories.swift` | 新增 | `MobileCapabilitiesRepository`、`ResearchRunsRepository`（缓存+SSE+对账）、`MemoryRepository`、`TradingMandatesRepository`；`APIError.isEndpointMissing` |
| `Core/Persistence/Repositories.swift` | 修改 | `RepositoryContainer` 接入新仓储；`canUseCache` 改为 internal |
| `Core/API/APIClient.swift` | 修改 | 新增 `streamGet`（GET SSE，契约 events 接口），`stream` 改为共用 `openStream` |
| `App/AppState.swift` | 修改 | `mobileCapabilities` 加载（登录/恢复时）、`pendingResearchRunID` 深链、`handlePushRoute` 支持 `research_run`、注销清理 |
| `Features/Research/ResearchRunsView.swift` | 新增 | 研究任务列表/详情/证据页/时间线/启动表单；不可用态、stale 标识、免责声明 |
| `Features/Research/ResearchView.swift` | 修改 | 分段新增 "Research runs"，深链导航 |
| `Features/Agent/AgentView.swift` | 修改 | 工具栏"启动研究"入口（能力门控） |
| `Features/Account/MemoryControlsView.swift` | 新增 | 记忆开关/同意/提案审批/删除/清空二次确认/导出/状态展示 |
| `Features/Account/TradingSafetyView.swift` | 新增 | Mandate 列表/详情/风险限制/PAPER·SHADOW·LIVE_DISABLED 展示；暂停恢复门控 |
| `Features/Account/AccountView.swift` | 修改 | 新增 "Research & safety" 分区（Memory / Trading Safety 入口） |
| `Resources/en.lproj/Localizable.strings`、`zh-Hans.lproj/Localizable.strings` | 修改 | 新增中英文案 |
| `PureGammaTests/MobileModelsDecodingTests.swift` | 新增 | DTO 解码容错测试（12 项） |
| `PureGammaTests/ResearchRunEventTests.swift` | 新增 | SSE 事件/未知事件/状态机测试 |
| `PureGammaTests/TradingSafetyPolicyTests.swift` | 新增 | LIVE 永不可操作/暂停恢复门控/能力默认关闭/端点缺失判定/Memory 同意测试 |

### Android（`apps/android`，Web Product Shell）

| 文件 | 类型 | 说明 |
|---|---|---|
| `app/.../model/MobileModels.kt` | 新增 | 领域模型 + JSON 容错解析（与既有 `Models.kt` 风格一致） |
| `app/.../data/remote/dto/MobileApiDtos.kt` | 新增 | Gson DTO（字段可空，缺失即 false） |
| `app/.../data/remote/PureGammaApi.kt` | 修改 | 新增契约 v1 全部 Retrofit 端点 |
| `app/.../data/repository/MobileRepositories.kt` | 新增 | `MobileRepository`（capabilities 404/501 → 全部不可用；5xx 抛出） |
| `app/.../AppViewModel.kt` | 修改 | `mobileCapabilities` 状态与加载、`handleDeepLink`、FCM `research_run` 路由、`openProductRoute` 白名单、登出清理 |
| `app/.../ui/PureGammaApp.kt` | 修改 | `ProductWebOverlay`（受信 Web 产品覆盖层）；Research 页 Harness 入口；Account 页服务能力行（Memory/Trading/LIVE_DISABLED） |
| `app/.../ui/WebProductScreen.kt` | 修改 | WebView 域名白名单改为由 `BuildConfig` 派生（不再硬编码扩散） |
| `app/.../data/remote/SseClient.kt` | 修改 | 构造函数支持注入 baseUrl（测试可注入 MockWebServer；默认行为不变） |
| `app/.../MainActivity.kt` | 修改 | 深链分发改为 `handleDeepLink`（兼容 OAuth 与研究路由） |
| `app/src/main/AndroidManifest.xml` | 修改 | 新增 `puregamma://research/runs/*` intent-filter |
| `app/build.gradle.kts` | 修改 | 新增 `PRODUCT_WEB_BASE_URL` BuildConfig（可经 `PG_PRODUCT_WEB_BASE_URL` 覆盖） |
| `app/.../res/values/strings.xml`、`values-zh-rCN/strings.xml` | 修改 | 新增中英文案 |
| `app/src/test/.../model/ResearchRunStateTest.kt` | 新增 | 状态机/LIVE 门控测试 |
| `app/src/test/.../data/remote/SseClientCompatTest.kt` | 新增 | SSE 未知事件/非 JSON/断流/429 测试 |
| `app/src/test/.../data/repository/MobileRepositoryTest.kt` | 新增 | capabilities 404/501/500/解析、mandate 环境、404 不可用测试 |

## 2. 未完成后端接口清单

| 接口 | 状态 | 移动端当前表现 |
|---|---|---|
| `GET /api/mobile/capabilities` | ❌ 未实现 | 拉取失败 → 全部新入口"功能暂不可用" |
| `POST/GET /api/research/runs*`（cancel/retry/artifacts/evidence/events） | ❌ 未实现 | 404 → 列表/详情显示不可用 |
| `GET/PATCH /api/memory/*`（items/proposals/clear/export） | ❌ 未实现 | 404 → Memory 页显示不可用 |
| `GET /api/trading/mandates*`（status/risk/pause/resume） | ❌ 未实现 | 404 → Trading Safety 显示不可用 |
| 推送 `route: research_run` | ❌ 未发送 | 两端深链处理已就绪，等待服务端推送 |

## 3. 不影响现有功能的验证结果

### iOS（已重新执行，评审修复后）

- [x] `xcodebuild build`（iPhone 17 Pro 模拟器，Swift 6 严格并发）：**通过，0 error**。
- [x] `xcodebuild test` 全量单元测试：**通过（exit=0）**，含既有测试与新增 `MobileModelsDecodingTests`、`ResearchRunEventTests`、`TradingSafetyPolicyTests`、`MobileGateTests`（ID 校验/门控/缓存命名空间隔离）。
- [x] 未修改：`AppRootView` Tab 结构、`AuthenticationService`/PKCE/Apple 登录、`PushAppDelegate`、`KeychainTokenStore`、既有 API 路径与 DTO。

### Android（IDE 静态诊断，已执行；本机无 JDK，未跑 Gradle）

- [x] 全部修改/新增 Kotlin 文件 IDE 诊断 **0 error**。
- [x] 未修改：`SecureTokenStore`、`MobileOAuth`、`PureGammaMessagingService`、`ApiProvider` 拦截器、既有 Tab 页面结构。
- [ ] Gradle 单元测试**未在本机执行**（无 JDK 17）。已更新 `MobileRepositoryTest`（门控/幂等/LIVE 拦截/ID 校验）与 `SseClientCompatTest`，待有 JDK 环境执行。

### 回归影响面（代码级确认）

| 既有功能 | 影响 | 依据 |
|---|---|---|
| Agent 对话 | 无 | `AgentView` 仅新增工具栏按钮与 sheet；流式逻辑未动 |
| Research / Portfolio / Billing | 无 | 原仓储与页面逻辑未动；`ResearchView` 仅新增一个分段 |
| Signals / Playbooks / Backtest / Options | 无 | 未触碰 |
| Google/Apple 登录、PKCE | 无 | 认证文件未改 |
| 自动邮件 / 服务器自动化 | 无 | 纯移动端变更 |
| 推送与深链 | 兼容 | 新增 case 分支，旧 route 行为不变 |
| 安全策略 | 无 | 无新 SDK、无新密钥存储、无下单能力 |

## 4. 验收标准对照

- [x] 原有功能回归：iOS 全量测试通过；Android 未改既有逻辑路径
- [x] Agent / Research / Portfolio / Billing 不受影响（代码级确认）
- [x] 自动邮件 / 服务器自动化不受影响（本次无服务端改动）
- [x] Token 不出现在日志与源码；移动端无交易所 Secret；无下单能力
- [x] LIVE 永远不可用（客户端硬约束 + 测试覆盖）
- [x] Harness 不可用时其他功能正常（新入口独立降级）
- [x] 记忆具备用户隔离、删除与同意机制
- [x] 所有状态以服务端为准；无假数据掩盖未完成接口

## 5. 评审修复轮变更（2026-08-15 第二轮）

对应评审六项"必须修复"：

### 5.1 Repository 层统一 capabilities 门控

| 端 | 文件 | 修复 |
|---|---|---|
| iOS | `Core/Models/MobileDomainModels.swift` | 新增 `MobileGateError`、`MobileInput`（ID/文本/dataSources/clear scope 白名单与长度限制）、`Error.mobileAPIError` 映射 |
| iOS | `Core/Persistence/MobileRepositories.swift` | 新增 `MobileCapabilitiesStore` + `MobileGate`；三个仓储每个方法调用前门控；`pause/resume` 先 GET 校验环境、幂等、LIVE 抛错不发请求；全部路径参数走 `MobileInput.id` |
| iOS | `Core/Persistence/Repositories.swift` | `RepositoryContainer` 持有 `capabilitiesStore` 并注入各仓储 |
| iOS | `App/AppState.swift` | 登录/恢复时写入门控 store + 设置缓存命名空间；注销/401/删除账户重置 |
| Android | `data/repository/MobileRepositories.kt` | `MobileRepository` 注入 `capabilitiesProvider`，每方法门控；`MobileFeatureException`；ID/dataSources 校验；pause/resume 先 GET 校验 + 幂等 + LIVE 拦截 |
| Android | `AppViewModel.kt` | 注入能力提供者；`openProductRoute` 增加 capabilities 第二层门控；注销 `CookieManager.removeAllCookies` |

### 5.2 路径参数编码与校验

- iOS `MobileInput` / Android `requireId`：run_id/mandate_id/proposal_id/item_id 强制 `[A-Za-z0-9_-]{1,64}`；`dataSources` 服务端白名单子集 + 去重 + ≤8 项 + ≤32 字符；name≤100 / prompt≤4000；clear scope ∈ {all, short_term, mid_term}。非法输入在 Repository 层拦截，不发网络请求。

### 5.3 用户隔离缓存

- `ResponseCache` 支持命名空间 `{environment}:{user_id}:{key}`；`RepositoryContainer.setCacheNamespace(userID:)` 登录后调用；`clearCaches()` 重置命名空间并清空目录；`ResponseCache` 目录可注入（测试用独立临时目录，避免并行测试互扰）。

### 5.4 WebView / Cookie / Bridge 边界（Android）

- `shouldOverrideUrlLoading`：禁 `javascript/file/content/data` 及自定义 Scheme；`mailto/tel` 仅最简单形式；白名单外外跳系统浏览器。
- `shouldInterceptRequest`：主框架请求重新校验（重定向后最终 URL 必须是受信域名 + HTTPS）。
- 阻断下载；第三方 Cookie 保留（登录流程需要）并注释边界；注销清 Cookie；Bridge 保持最小（无 Token/API/命令能力）；Debugging 仅 DEBUG。
- `ProductWebOverlay` 无法绕过门控：`openProductRoute` 双层校验（路径白名单 + capabilities）。

### 5.5 iOS SSE 生命周期与 Memory 一致性

- `ResearchRunDetailViewModel.stop()`：视图 `.onDisappear` 与进入后台取消订阅；回前台先查服务端再重订阅；重连限 3 次（2s 退避）→ 轮询 10s→30s；最终状态永远以 `GET /runs/{id}` 为准。
- Memory 乐观删除改为快照回滚 + 失败提示；清空等待服务端确认后提示完成；操作后重拉列表。

### 5.6 Git 工作区卫生

- 见 `GIT_HYGIENE.md`：移动端/文档/无关变更的拆分提交方案，以及 `mobile-release.yml` 与 `apps/ios/releases/README.md` 删除的确认要求。

### 5.7 新增/更新测试

- iOS 新增 `PureGammaTests/MobileGateTests.swift`（ID 校验、门控、缓存命名空间隔离、未知环境降级）；全量 `xcodebuild test` 通过。
- Android 更新 `MobileRepositoryTest`（门控零请求、LIVE 拦截、幂等、dataSources 白名单、404 语义）；`SseClientCompatTest` 保持。IDE 诊断 0 error；Gradle 执行待有 JDK 17 的环境。
