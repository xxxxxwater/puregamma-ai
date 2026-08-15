# LIVE Trading — 生产部署说明

## 1. 前置条件(不满足不得开放 LIVE)

- Ledger、Risk Engine、对账、Kill Switch、Secret 管理、审计**全部落地**(本
  批次已完成,见 STATUS.md);
- 16GB 单机:各容器内存上限已在 `docker-compose.production.yml`
  (api 640m / worker 768m / postgres 768m / redis 512m / runtime 512m /
  web 384m / scheduler 192m / caddy 128m),系统余量 > 4GB;
- 日志限制:compose 已为 api/worker/scheduler 配置 `json-file`
  `max-size 10m × 3`(其余服务沿用镜像默认,按需加)。

## 2. 环境变量(见 .env.example 的 LIVE 段)

```bash
LIVE_TRADING_ENABLED=false                 # 总闸
LIVE_TRADING_DEPLOYMENT_APPROVED=false     # 部署标记
LIVE_TRADING_PROVIDER=                     # 券商标识(未配置时 gateway 拒绝)
LIVE_TRADING_VENUE=MOCK
LIVE_TRADING_ALLOWED_SYMBOLS=BTCUSDT,ETHUSDT
LIVE_TRADING_GATEWAY=mock                  # 接真实券商前保持 mock
LIVE_CREDENTIAL_ENCRYPTION_KEY=<fernet>    # 或依赖 ENCRYPTION_MASTER_KEY 派生
```

## 3. 上线顺序

1. 部署代码 + `alembic upgrade head`(0026);
2. **保持** `LIVE_TRADING_ENABLED=false`;启动全部服务;
3. Admin:创建 broker connection(密文凭据)并 `POST /api/trading/connections/test`;
4. Admin:`POST /admin/trading/live-approvals` 逐个批准试点用户(小额);
5. 创建/批准 `execution_mode=live` 的 Mandate(限额、白名单必须完整);
6. 开启部署标记 → 重启 → 在 `GET /api/trading/safety-status` 验证所有 checks;
7. 最后才打开 `LIVE_TRADING_ENABLED` 并把 `LIVE_TRADING_GATEWAY=nautilus`。

## 4. 服务器重启策略(强制)

- 重启后 LIVE Mandate **不自动恢复**:所有 `paused=false` 的 live Mandate 由
  运维在完成以下动作后手动恢复:
  1. `POST /api/trading/connections/test` 验证连接;
  2. 手动执行一次 `puregamma.daily_live_reconciliation`;
  3. 对账 OK → admin 恢复 Mandate。

## 5. 备份与告警

- 每日加密异地备份:`deploy/live-trading/offsite-encrypted-backup.sh`
  (gpg AES256 / age;本地仅存密文;需 `S3_BUCKET`);
  cron:`30 1 * * * ... >> /var/log/puregamma-encrypted-backup.log 2>&1`
- 资源/队列告警:`deploy/live-trading/resource-alerts.sh`
  (磁盘 85% / 内存 90% / load 8 / unhealthy 容器 / Celery 队列 200);
  cron:`*/5 * * * * ...`
- 应用层告警沿用 `ops_alert.notify_ops`(对账差异、风控触发时调用)。

## 6. Celery 预算(单机硬约束)

- worker `--concurrency=${WORKER_CONCURRENCY:-2}`(≤2);
- 行情 5–15s、订单状态 5–10s、余额/持仓与 NAV 30–60s;
- Harness 全局并发 1–2、单用户研究并发 1(既有配置)。

## 7. 恢复后检查清单

1. 连接健康;2. 对账;3. 未确认订单查询交易所;4. NAV 重算;
5. 确认 `safety-status` 全绿后才允许新订单。
