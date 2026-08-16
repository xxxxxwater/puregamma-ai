# Feature Flag 发布说明（移动端）

## 原则

- 移动端**只读服务端** capabilities（`GET /api/mobile/capabilities`），不使用 App 内静态配置做放行判断。
- 默认全部关闭。服务端未返回某字段 → 客户端视为 `false`（DTO 全部可空/容错）。
- 服务端接口缺失（404/501）→ `serverContractAvailable=false` → 全部新功能显示"功能暂不可用"。

## Flag 清单与移动端行为

| Flag（服务端） | 默认 | 移动端行为（false 时） | 移动端行为（true 时） |
|---|---|---|---|
| `harness_research_enabled` | off | Research→Runs 入口显示"功能暂不可用" | 显示研究任务列表/详情（后端接口未落地时仍按 404 显示不可用） |
| `user_can_start_research` | off | 隐藏/禁用"启动研究"按钮 | 允许提交任务（服务端二次校验额度/权限） |
| `harness_retry_enabled` | off | 隐藏"重试"按钮 | 对 failed/canceled/timed_out 显示重试 |
| `memory_service_enabled` | off | Account→Memory 显示不可用 | 显示记忆开关/提案/删除/清空/导出 |
| `user_can_manage_memory` | off | Memory 页只读或不可用 | 允许修改 |
| `auto_trading_enabled` | off | Account→Trading Safety 显示不可用 | 显示 Mandate 只读列表 |
| `user_can_view_trading_mandates` | off | 隐藏 Mandate 入口 | 展示 Mandate |
| `paper_trading_enabled` / `shadow_trading_enabled` | off | 对应环境标记为 OFF | 展示 PAPER/SHADOW 状态徽章 |
| `user_can_pause_mandates` | off | 不渲染暂停/恢复按钮 | 仅对 PAPER/SHADOW 渲染按钮（服务端再次校验） |
| `live_trading_enabled` | 恒 off | — | **即使为 true，移动端仍不提供 LIVE 入口**（客户端硬约束） |
| `app_min_version` | — | 低于该值时提示升级（不强制退出） | — |
| `maintenance_message` | — | 在相关入口展示维护文案 | — |

## 发布节奏建议

- **阶段 1（本分支）**：capabilities 契约就绪；移动端全部入口以服务端为准，后端未落地 → 全员看到"功能暂不可用"（无假数据）。可随现有 App 发版，零风险。
- **阶段 2**：后端实现 `/api/mobile/capabilities` + `/api/research/runs*`，逐步打开 `harness_research_enabled` 给灰度用户。
- **阶段 3**：实现 `/api/memory/*`，打开 `memory_service_enabled`。
- **阶段 4**：实现 `/api/trading/mandates*`，打开 `auto_trading_enabled`（仅 PAPER/SHADOW）。
- LIVE：不在本方案范围内；开放必须经独立安全审查。

## 回滚开关

- 任何功能可在服务端把对应 Flag 置 false，移动端无需发版即恢复隐藏/不可用态。
- 移动端自身回滚见 `ROLLBACK_PLAN.md`。
