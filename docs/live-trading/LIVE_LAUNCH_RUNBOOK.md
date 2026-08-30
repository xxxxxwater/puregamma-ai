# PureGamma 实盘 LIVE 上线 Runbook

> 依据 `LIVE_LAUNCH_ARCHITECTURE.md` 与 `PROMPT_MVP_LIVE_BACKEND.md`。
> 每一阶段都有明确的回滚命令;任何一步不满足门控,系统诚实保持
> `LIVE_DISABLED`,绝不伪造成功。

## 0. 前置条件(硬性)

- [ ] 代码已包含 `packages/live_trading/binance_spot_gateway.py`(真实网关);
- [ ] `alembic upgrade head` 单 head(0026),生产库干跑通过;
- [ ] `pytest tests/security/test_live_trading_gateway.py tests/security/test_live_trading_foundation.py` 全绿;
- [ ] 服务器 16GB 单机:容器内存上限、日志滚动(api/worker/scheduler
      10m×3)、加密异地备份、资源告警脚本生效;
- [ ] 静态门保留全 OFF(`LIVE_TRADING_ENABLED=false`、
      `LIVE_TRADING_DEPLOYMENT_APPROVED=false`、`LIVE_TRADING_GATEWAY=mock`);
- [ ] 旧运行时 LIVE 永远关闭:`NAUTILUS_LIVE_TRADING_ENABLED=false`、
      `NAUTILUS_ALLOW_LIVE_ORDER=false`、`NAUTILUS_ALLOW_WITHDRAWAL=false`、
      `NAUTILUS_ALLOW_TRANSFER=false`。

## 1. 测试网/小额联调(静态门仍全 OFF)

1. 生成 Fernet 密钥并写入 `.env`:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   # LIVE_CREDENTIAL_ENCRYPTION_KEY=<上一步输出>
   ```
2. 配置(生产 `.env`):
   ```bash
   LIVE_TRADING_PROVIDER=binance_spot
   LIVE_TRADING_VENUE=BINANCE
   LIVE_TRADING_ALLOWED_SYMBOLS=BTCUSDT,ETHUSDT
   LIVE_TRADING_GATEWAY=binance
   LIVE_TRADING_BINANCE_BASE_URL=https://testnet.binance.vision   # 演练基址
   LIVE_TRADING_ENABLED=false                                      # 仍然关闭!
   LIVE_TRADING_DEPLOYMENT_APPROVED=false
   ```
3. `docker compose -f docker-compose.production.yml up -d api worker scheduler`
   → `GET /api/trading/safety-status` 应显示 `LIVE_DISABLED`
   (`live_trading_enabled` 项 false),前端 manifest 中
   `puregamma.live-trading.enabled=false`。
4. 演练用户自助绑定(测试网密钥):
   `POST /api/trading/connections`(provider=binance_spot) →
   连接应为 `HEALTHY` 且 `permissions.safe=true`;故意提交一把开启提现的
   密钥 → 应 400 `Connection rejected` 且连接 `ERROR`。
5. admin 创建/审批 Mandate(execution_mode=live、environment=production、
   极小限额 ≤ `LIVE_TRADING_DEFAULT_MAX_NOTIONAL`)、`POST /admin/trading/
   live-approvals` 审批 1–2 个内部用户。
6. 门仍关闭 ⇒ 下单被拒:`LIVE disabled: live_trading_enabled` —— 确认后
   进入下一阶段。

**回滚**:`LIVE_TRADING_GATEWAY=mock` → 重启 api/worker/scheduler。

## 2. 打开部署标记,验证门控全链路(仍不开总闸)

1. `LIVE_TRADING_DEPLOYMENT_APPROVED=true` → 重启 api/worker/scheduler。
2. `GET /api/trading/safety-status` 逐项核对:静态门(除 `LIVE_TRADING_ENABLED`)
   全绿、用户审批、Mandate 审批、连接健康、对账 ok、Kill Switch 全关。
3. 手动跑一次对账:
   ```bash
   docker compose -f docker-compose.production.yml exec worker \
     celery -A packages.workers.celery_app call puregamma.daily_live_reconciliation
   ```
   对账 `ok` 后才继续。

**回滚**:`LIVE_TRADING_DEPLOYMENT_APPROVED=false` → 重启。

## 3. 打开总闸,首单验证(严格按序)

1. `LIVE_TRADING_ENABLED=true` → 重启 api/worker/scheduler。
2. `GET /api/trading/safety-status` 全绿后,按
   `FIRST_ORDER_VERIFICATION.md` 走完首单(预览→确认→成交→Ledger→NAV→
   对账,核对 trace_id)。
3. 演练应急(每项都执行一次):
   - 全局 Kill Switch:`POST /admin/trading/kill-switch
     {"scope":"global","active":true,"reason":"drill"}` → 新单被拒、
     撤单/查询可用 → 管理员 release;
   - 环境层回滚:`LIVE_TRADING_ENABLED=false` → 重启 → safety-status
     回到 LIVE_DISABLED → 恢复;
   - 加密备份恢复:按 `ROLLBACK.md` 在演练库执行一次完整恢复。
4. 全部通过后按 `FIRST_ORDER_VERIFICATION.md` 归档首单报告。

**回滚**:`LIVE_TRADING_ENABLED=false`(或 Kill Switch)→ 重启。

## 4. 灰度放量

1. 每用户独立审批(`live_user_approvals`),首期 `max_total_notional`
   保持 ≤ 1000;
2. 新增用户 = 审批 → 建 Mandate → 连接健康 → 对账 ok → 下单;
3. 观察 `sync_live_balances_and_positions` / `refresh_live_market_prices`
   日志与资源告警(磁盘 85% / 内存 90% / load 8 / Celery 队列 200);
4. 任何异常按「一键关闭」处理,复盘后再放量。

## 一键关闭(任何时刻)

```bash
# 应用层(最快,保留查询/撤单/记成交/对账)
curl -X POST /admin/trading/kill-switch \
  -d '{"scope":"global","active":true,"reason":"emergency"}'
# 环境层(彻底)
# .env: LIVE_TRADING_ENABLED=false
docker compose -f docker-compose.production.yml up -d api worker scheduler
```

## 重启恢复(强制)

服务器重启后 LIVE Mandate **不自动恢复**;运维必须:
1. `POST /api/trading/connections/test` 验证连接;
2. 手动执行 `puregamma.daily_live_reconciliation`;
3. 对账 OK → admin 恢复 Mandate;
4. UNKNOWN 订单只查询不重发(`puregamma.sync_live_order_statuses`)。

## 验收清单(交付判定)

- [ ] 真实网关单测 + 端到端测试全绿;
- [ ] 静态门全 OFF 时安全状态恒为 LIVE_DISABLED;
- [ ] 不安全 API Key 被硬拒绝并告警;
- [ ] 提交超时订单为 UNKNOWN 且仅被提交一次;
- [ ] 首单报告完成并归档(见 FIRST_ORDER_VERIFICATION.md);
- [ ] 应急演练(开关/回滚/恢复)全部通过。
