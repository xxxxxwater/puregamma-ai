# 回滚方案（Rollback Plan）

## 设计要点：本次改动全部"增量 + 服务端门控"

- 所有新功能默认关闭，以服务端 capabilities 为准。
- 后端接口缺失（404/501）时客户端只显示"功能暂不可用"，不渲染操作按钮。
- 因此即便不做代码回滚，仅把服务端 Flag 保持关闭，用户侧行为即等同于升级前。

## 快速回滚（推荐，秒级）

1. 服务端保持 `HARNESS_RESEARCH_*`、`MEMORY_SERVICE_ENABLED`、`AUTO_TRADING_*` 全部 false（当前默认即如此）。
2. 不部署 `/api/mobile/capabilities` 之外的新接口。
3. 移动端表现：Account/Research 中新增入口全部为灰色"功能暂不可用"；LIVE 恒显示 Disabled。

## App 版本回滚

| 平台 | 操作 |
|---|---|
| iOS | 恢复上一个 App Store 构建；本分支未改 Tab 结构、登录、Push、既有 API 路径，旧包与新后端兼容。 |
| Android | 恢复上一个 Play 构建（Web Product Shell 的 WebView 域名白名单由 BuildConfig 派生，与旧包行为一致）。 |

## 数据/缓存回滚

- 新缓存键：iOS `research-runs`（ResponseCache）；缓存目录随 `clearCaches()` 清空，用户重新登录后自动重建，无持久化 schema 变更。
- 无本地数据库迁移（本次未新增 DB/DataStore）。

## 风险点与预案

| 风险 | 预案 |
|---|---|
| capabilities 接口上线但返回异常 | 客户端容错：字段缺失按 false，请求失败按全部不可用，不缓存"可用"结论 |
| 研究接口上线但字段变化 | DTO 全部可选字段 + 未知字段忽略；状态未知回退 `idle`，不崩溃 |
| SSE 新增事件类型 | 解析器忽略未知事件，绝不抛错（两端测试覆盖） |
| LIVE 被服务端误开 | 客户端硬约束：`liveActionAllowed` 恒 false，不渲染任何 LIVE 操作 |

## 回滚触发条件

- 新功能任一接口出现高 5xx 率（仅影响新入口，不影响既有功能）。
- 研究/记忆/交易页面出现崩溃级缺陷（页面隔离，可单入口关闭）。
- 既有功能回归失败（Agent/Research/Portfolio/Billing/登录/推送任一受损）→ 立即走"快速回滚"。

## 验证方式（回滚后）

1. iOS：`xcodebuild test` 全量通过；手工冒烟登录 → Today/Agent/Research/Portfolio/Account。
2. Android：`./gradlew :app:testDebugUnitTest`；手工冒烟同上。
3. 服务端：确认 `/api/mobile/capabilities` 未部署或全 false。
