# 2.2 预部署 — 未完成接口清单

> 原则:404/501 只用于未实现阶段;已实现的接口必须返回契约字段;5xx 不得被前端
> 吞成 unavailable;所有接口有 user ownership 校验;path id 格式校验;金额用
> Decimal/string。

## 未实现(移动端契约,诚实 404)

| 接口 | 说明 | 前端行为 |
|---|---|---|
| `POST /api/research/runs` | Harness 研究任务创建(契约 v1) | capabilities `user_can_start_research=false`;入口"功能暂不可用" |
| `GET /api/research/runs`、`GET /api/research/runs/{id}` | 列表/详情 | 同上;PR1 Web 详情页 SSE 断线回退轮询,404 不误标失败 |
| `GET /api/research/runs/{id}/events`(SSE) | 事件流 | 同上 |
| `GET /api/research/runs/{id}/evidence` | 证据 | 同上 |
| `GET/PATCH /api/memory/settings`、`/api/memory/proposals`、approve/reject/delete/export/clear | Memory 服务 HTTP 层 | capabilities `user_can_manage_memory=false`;Memory 页经 CapabilityGate 显示不可用 |

底层已就绪:harness_research_runs/状态机/artifact 表、memory 包与表、SSE 事件
模型;缺的是 HTTP 契约层(下一迭代)。

## 已实现(本轮验证)

| 接口 | 验证 |
|---|---|
| `GET /api/mobile/capabilities` | 200,诚实布尔(见 SMOKE_RECORD) |
| `GET /api/trading/mandates`、`/{id}`、`/{id}/pause`、`/{id}/resume` | 200/所有权校验 |
| `GET /api/trading/safety-status` | 200,LIVE_DISABLED |
| `GET /api/portfolio/nav`、`/history`、`/positions` | 200,NAV null 不伪造 |

## 契约字段补充

`/api/mobile/capabilities` 额外返回 `membership_tier`(白银/黄金一致性),对既有
解码器向后兼容(移动端忽略未知字段)。
