# 移动端升级安全检查清单（Security Checklist）

适用：PureGamma iOS 原生客户端 + Android 客户端（本次升级范围）

## 1. 密钥与凭证

- [x] Token 不进入日志：iOS `APIClient.logFailure` 只记录路径与状态码；Android OkHttp 日志 `redactHeader("Authorization")`，生产 `Level.NONE`。
- [x] Token 不出现在客户端源码：无硬编码 token、key、secret。
- [x] iOS Token 存 Keychain（`KeychainTokenStore`），未迁移。
- [x] Android Token 存 Android Keystore（`SecureTokenStore`），未迁移。
- [x] 移动端不保存：交易所 API Secret、私钥、模型密钥、Stripe Secret、数据库凭证（本次零新增此类存储）。
- [x] Memory 界面明文提示"永不保存"清单（私钥/Secret/卡号/Token/凭证/未确认交易意图/未验证 Harness 推论/自动交易指令）。

## 2. 网络与域

- [x] iOS 生产强制 HTTPS（`APIConfiguration` 在 production 环境校验 scheme）。
- [x] Android `usesCleartextTraffic=false`；WebView `MIXED_CONTENT_NEVER_ALLOW`。
- [x] Android WebView 域名白名单由 `PRODUCT_WEB_BASE_URL`/`API_BASE_URL`（BuildConfig）派生，生产为 `app.puregamma.ai`、`api.puregamma.ai`。
- [x] 明确禁止 `javascript:`、`file:`、`content:`、`data:` 及任意自定义 Scheme（`shouldOverrideUrlLoading` 拦截）。
- [x] 主框架资源经 `shouldInterceptRequest` 重新校验：重定向后的最终 URL 必须是受信域名 + HTTPS；子资源（CDN 字体/图片）不受影响。
- [x] 阻断 WebView 下载（`setDownloadListener` 空实现），不扩大文件权限。
- [x] `mailto:`/`tel:` 仅允许最简单形式（无参数、单一地址、正则白名单），防参数滥用。
- [x] 第三方 Cookie：保持开启（既有 Web 产品 OAuth 登录流程所需）；边界为白名单域名 + 主框架复验 + **注销时 `CookieManager.removeAllCookies`**。
- [x] WebView 不开任意 URL、无任意 JavaScript Bridge（仅保留既有 `PureGammaAndroid` 触感桥：无 Token/API/用户信息读取能力，不接受 URL/命令参数）；`WebContentsDebuggingEnabled` 仅 DEBUG。
- [x] `ProductWebOverlay` 不能绕过 Native capabilities：`openProductRoute` 双层门控（路径白名单 + 服务端 capabilities），未开启的能力无法打开对应 Web 路由。
- [x] 深链仅处理 `puregamma://oauth/*`、`puregamma://research/runs/*`，其余忽略。

## 3. 交易边界（最高优先级）

- [x] 移动端无下单接口调用（未引入任何 order 端点/SDK）。
- [x] 未新增交易所/券商 SDK（无 IBKR/Plaid/Moralis SDK 变更；既有只读连接保留）。
- [x] LIVE 恒为 `LIVE_DISABLED`：双端 `liveActionAllowed` 恒 false，UI 不渲染按钮，**Repository 层同样拦截（不发网络请求）**。
- [x] 暂停/恢复仅限 PAPER/SHADOW + `user_can_pause_mandates=true`：双端 Repository 先 GET Mandate 校验环境，已暂停/已恢复时幂等返回；服务端二次校验。
- [x] 暂停/恢复后重新 GET status（以服务端状态为准，不依据本地 paused 认定成功）。
- [x] 服务端 403/409/风控拒绝按原样转为明确错误展示（错误信封 message 透传）。
- [x] 未知 `environment` 值降级为 `unavailable`，绝不当作可操作环境（双端测试覆盖）。
- [x] 风险限制只读展示，无本地修改接口。
- [x] 额度/权限/资格全部以服务端返回为准；无本地判定。

## 3b. Repository 层统一 capabilities 门控（评审修复）

- [x] iOS：`MobileGate` + `MobileCapabilitiesStore`，`ResearchRunsRepository`/`MemoryRepository`/`TradingMandatesRepository` 每个方法调用前校验；capabilities 缺失/为 false 直接抛 `MobileGateError`，不发网络请求。
- [x] Android：`MobileRepository` 构造注入 `capabilitiesProvider`，同样每个方法先门控，`MobileFeatureException` 拦截。
- [x] UI 门控仅是展示层保护，不再是唯一安全边界；服务端仍做最终权限校验。
- [x] 路径参数：`MobileInput`（iOS）/ `requireId`（Android）对 run_id/mandate_id/proposal_id/item_id 做 `[A-Za-z0-9_-]{1,64}` 校验；`dataSources` 白名单+数量/长度限制；name/prompt 长度限制；clear scope 白名单。

## 4. 研究与记忆

- [x] 研究结果区分 verified / partial / degraded / failed / incomplete，恒附免责声明。
- [x] 无伪造研究结果/进度/状态/收益；接口缺失时显示"功能暂不可用"。
- [x] 记忆按用户隔离展示；Proposal 需同意；删除/清空有确认；导出由服务端生成签名链接。
- [x] 记忆界面不展示原始内部 Prompt/完整上下文/内部系统字段（契约层面 `content_preview` 脱敏）。

## 5. 会话与缓存

- [x] 401 → 自动退出（iOS `onUnauthorized` / Android `AuthErrorInterceptor`）。
- [x] 注销/删除账户 → `clearCaches()`（两端均已覆盖新缓存键）；Android 同时 `removeAllCookies`。
- [x] **缓存用户隔离**：`ResponseCache` 支持命名空间 `{environment}:{user_id}:{key}`（评审修复），登录成功后由 AppState 设置，切换账号/注销后重置并清空，杜绝跨账号 stale 数据。
- [x] 离线缓存展示必须带 stale 标识（`LoadState.stale` / `StaleDataBanner`）。
- [x] 旧缓存不覆盖服务端新状态（缓存仅在请求失败且可容错时作为展示回退）。
- [x] 能力发现不做本地"可用"缓存，每次登录重拉。

## 6. SSE / 推送

- [x] SSEParser 对未知事件名/未知类型不抛错（iOS 测试覆盖；Android `SseClient` 非 JSON data 降级为空对象，测试覆盖）。
- [x] SSE 断线不把任务标为失败：iOS 重连（限 3 次、2s 退避）→ 轮询（10s→30s）→ 以 `GET /runs/{id}` 为准；**视图离开/进入后台即取消订阅（评审修复）**，回前台先查服务端再重订阅。
- [x] 推送深链 `research_run`：点击后按 run_id 查服务端最终状态再展示。

## 7. 本地化与无障碍

- [x] 新增文案均提供 en / zh（iOS Localizable.strings；Android values / values-zh-rCN）。
- [x] 深色模式沿用既有主题体系；Dynamic Type / TalkBack 使用系统组件默认能力，关键行添加 accessibility 标签。

## 未覆盖项（需后端配合）

- [ ] 后端接口落地后，按契约联调并补端到端回归（当前接口 404/501 → 不可用态，已按此验证）。
- [ ] App Store / Play 审核通过前的正式发布。
