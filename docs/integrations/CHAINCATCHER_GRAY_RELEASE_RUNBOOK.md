# 市场快讯（ChainCatcher + 其他 RSS）灰度上线 Runbook

> 配合 CHAINCATCHER_NEWSWIRE.md（架构）与 docs/review/CHAINCATCHER_NEWS_FEED_REVIEW.md（评审）使用。
> 命令在可出网的服务器执行（本机沙箱外网阻断，无法预验证 feed 可达性）。

---

## 0. 前置阻塞（上线前必须完成）

- [ ] ChainCatcher 商用书面确认：摘要再分发、商用流量、调用频率、缓存期限、署名样式、删除要求、SLA。未确认前仅灰度，不对外承诺 SLA。
- [ ] 8 个既有测试失败单独立项：通知模拟（test_notifications.py 6 例）+ Nautilus 回测假设（test_backtest_assumptions.py 等 2 例），与快讯无关，不阻塞灰度。

---

## 1. 预检：验证 feed 可达（200 + 非重定向）

RSS provider 拒绝 redirect 与 4xx，预检要同时看状态码与是否 301/302。

    feeds_id=(coindesk decrypt blockworks theblock cointelegraph dlnews bitcoinmagazine glassnode coinmetrics deribit messari)
    feeds_url=(https://www.coindesk.com/arc/outboundfeeds/rss https://decrypt.co/feed https://blockworks.com/feed https://www.theblock.co/rss.xml https://cointelegraph.com/rss https://www.dlnews.com/arc/outboundfeeds/rss/ https://bitcoinmagazine.com/feed https://insights.glassnode.com/rss/ https://coinmetrics.substack.com/feed https://insights.deribit.com/feed/ https://messari.io/rss)
    for i in ${!feeds_id[@]}; do
      code=$(curl -s -o /dev/null -w %{http_code} -A PureGamma-AI/1.0 --max-time 15 ${feeds_url[$i]})
      redir=$(curl -s -o /dev/null -w %{redirect_url} --max-time 15 ${feeds_url[$i]})
      echo ${feeds_id[$i]} code=$code redirect=${redir:-none}
    done

    echo ChainCatcher:
    curl -s -o /dev/null -w rss=%{http_code}:%{content_type} -A PureGamma-AI/1.0 https://www.chaincatcher.com/rss/clist
    echo
    curl -s --max-time 15 https://api.chaincatcher.com/v1/open-api/news-flash?type=flash&page=1&size=1&lang=zh-CN -H Accept:application/json | head -c 300

判定：期望全部 200；ChainCatcher REST 返回 JSON 且 result=1。若某源 NON200 或 REDIRECT，在 config/rss_sources.yaml 把该源 enabled: false（或改成最终跳转地址）。

---

## 2. 激活数据同步

环境变量（deploy/production.env 或根 .env）：

    DATA_SYNC_WORKER_ENABLED=true
    CHAINCATCHER_SYNC_ENABLED=true
    CHAINCATCHER_LANGUAGES=zh-CN,en,ja,ko
    CHAINCATCHER_SYNC_INTERVAL_MINUTES=5
    CHAINCATCHER_API_REFRESH_MINUTES=15

手动触发（需管理员登录，或管理后台 Data Sources 页点 Sync）：

    curl -X POST https://YOUR_API_DOMAIN/admin/data-sources/chaincatcher/sync -b YOUR_ADMIN_COOKIE
    curl -X POST https://YOUR_API_DOMAIN/admin/data-sources/rss/sync -b YOUR_ADMIN_COOKIE

查看运行历史（本次已修复 chaincatcher 走 ProviderSyncLog 正确分支）：

    curl -s https://YOUR_API_DOMAIN/admin/data-sources/chaincatcher/runs -b YOUR_ADMIN_COOKIE

---

## 3. 功能验收

- [ ] 管理后台 Data Sources：chaincatcher 与 rss 状态 HEALTHY，itemsIngested 增长。
- [ ] 管理后台 preview：chaincatcher 显示快讯/文章、出处、短摘要、无全文。
- [ ] /api/news：kind=flash&source=chaincatcher 有中文快讯；source=rss 有英文文章；symbol、q、游标翻页正常。
- [ ] 前端 /zh/news 与 /en/news：筛选、相对时间、原文跳转、language_fallback 提示、免责声明正常。
- [ ] Agent / 每日简报 / trending 能引用到 ChainCatcher 与 RSS 文档（rss alias 自动展开）。

---

## 4. 灰度与监控（建议 10% 24 小时）

- [ ] 观察：429、同步失败、距最后成功超 15 分钟、零入库、单源 DEGRADED。
- [ ] 观察 ChainCatcher REST 15 分钟节流与 RSS 5 分钟轮询是否在预期内。
- [ ] 观察 8 个新增 RSS 源 per-feed 健康，必要时停用坏源。
- [ ] 无误后全量开放。

---

## 5. 回滚

1. 停 ChainCatcher（保留其他 RSS）：CHAINCATCHER_SYNC_ENABLED=false 后重启 scheduler/worker。
2. 停单个 RSS 源：config/rss_sources.yaml 把该源 enabled: false，重新部署。
3. 整体停新闻流：DATA_SYNC_WORKER_ENABLED=false（连 binance/fintwit 一并停，谨慎）。
4. 前端无缓存风险：/api/news 用私有短缓存 max-age=15，回滚后约 15 秒失效。

---

## 附：本次部署前 Review 顺带修复
- apps/api/routers/admin.py：GET /data-sources/{provider_id}/runs 的文档 provider 白名单补 chaincatcher（此前误查 DataSourceSyncRun 返回空历史）。
- deploy/production.env.example：补 CHAINCATCHER_RSS_URL 与 CHAINCATCHER_API_BASE_URL。