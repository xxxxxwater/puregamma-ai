# 2.2 预部署 — 冒烟记录(2026-08-16,本地 sqlite 模拟)

环境:`APP_ENV=development`、内存 sqlite、`seed_all`;TestClient 直连。

| # | 项目 | 结果 |
|---|---|---|
| 1 | PostgreSQL 备份 | 本地无 docker,使用 `scripts/production-backup.sh` 路径核对:服务器 `/puregamma/data/nautilus_state` 存在且 compose 同路径(SSH 确认) |
| 2 | Alembic upgrade | `puregamma.db` → `0027_user_membership_tier`;`users.membership_tier` 列存在,默认 silver |
| 3 | API 启动 | app 导入 + 路由注册正常 |
| 4 | Web build | `pnpm typecheck` 通过;`pnpm lint` 无 error |
| 5 | worker/scheduler | `main()` 增加 Redis 单实例锁;重复启动被拒(锁 `pg:lock:scheduler`) |
| 6 | health check | `GET /health` → 200 |
| 7 | 登录 | JWT 签发正常(TestClient 全端点使用) |
| 8 | Agent SSE | 既有测试覆盖(未重跑 Playwright) |
| 9 | Portfolio/NAV | `GET /api/portfolio/nav` → 200 |
| 10 | Billing capabilities | `GET /billing/capabilities` → 200 |
| 11 | Admin 改 Silver/Gold | `PATCH /admin/users/{id}/tier {"tier":"gold"}` → 200(`plan=Max` 同步);`bronze` → 400 |
| 12 | Trading safety status | `GET /api/trading/safety-status` → 200,`state=LIVE_DISABLED` |
| 13 | global kill switch | 测试套件 `test_kill_switch_blocks_preview_and_allows_cancel` 通过 |
| 14 | backup restore 抽样 | 本地无法跑 PostgreSQL restore;命令与步骤见 ROLLBACK.md,staging 必做 |
| 15 | rollback 文档 | 本目录 ROLLBACK.md + docs/live-trading/ROLLBACK.md |

补充(契约):
- `GET /api/mobile/capabilities` → 200:`live_trading_enabled=false`、
  `user_can_view_trading_mandates=true`、`user_can_start_research=false`、
  `membership_tier=silver`
- `GET /api/trading/mandates` → 200
- `GET /api/research/runs` → 404(诚实未实现)
- `GET /api/memory/settings` → 404(诚实未实现)
