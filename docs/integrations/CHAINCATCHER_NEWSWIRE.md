# ChainCatcher 商业级快讯接入方案

## 产品目标

PureGamma 的 `Market Wire / 市场快讯` 是研究型新闻流，不是全文转载站，也不是自动交易触发器。首期提供：

- ChainCatcher 中文/英文快讯，按快讯、文章、来源、资产和时间窗口筛选；
- 60 秒前端自动刷新、游标分页、关键词搜索、原文跳转和明确出处；
- 快讯自动进入 PureGamma 现有的实体识别、情绪、事件去重、Agent 引用、日报热点和来源观点链路；
- 无外部数据时显示预热/不可用状态，绝不伪造示例新闻。

## 数据架构

```text
ChainCatcher RSS（低延迟） ─┐
                            ├─ ChainCatcherProvider ─ NormalizedDocument ─ /api/news ─ Web
ChainCatcher REST（多语言）─┘                              ├─ Agent evidence
                                                          ├─ Daily brief / push
                                                          └─ Trending entities
```

两条入口各司其职：

1. RSS 是快路径。工作进程默认每 5 分钟拉取，最多解析最新 200 条；目标端到端延迟不超过约 5–7 分钟。
2. REST API 官方说明约有 15 分钟缓存延迟，因此每 15 分钟调用一次，用于英文覆盖、原创标记、关键词和缺失记录回补；RSS 失败时立即作为降级路径调用。
3. 两路记录使用 `语言 + ChainCatcher 文章 ID` 合并。跨来源的事件仍使用 PureGamma 的稳定哈希与事件指纹去重。
4. `chaincatcher` 是独立存储/运维 provider，拥有单独健康状态、游标、熔断器、同步日志和调度；产品权限映射到既有 `rss` entitlement，因此不破坏现有套餐。
5. RSS 与 REST 都优先使用规范化 URL 中的文章 ID 作为合并键；REST `item.id` 只在 URL 不含 ID 时回退。RSS 语言来自 channel/entry language 并规范化为 BCP-47 风格值。

## 其他 RSS 新闻源（"其他 RSS"分类）

ChainCatcher 承担"快讯"，其余 RSS 源承担"文章"覆盖，统一由 `config/rss_sources.yaml` 配置（URL 不内嵌到业务服务），走 `rss` provider 与既有文档管道。当前启用源及可信度：

| 分组 | 源 | Feed | 可信度 |
| --- | --- | --- | --- |
| 综合新闻 | CoinDesk | https://www.coindesk.com/arc/outboundfeeds/rss | 0.82 |
| 综合新闻 | Decrypt | https://decrypt.co/feed | 0.72 |
| 综合新闻 | Blockworks | https://blockworks.com/feed | 0.80 |
| 机构/市场结构 | The Block | https://www.theblock.co/rss.xml | 0.84 |
| 综合广度 | CoinTelegraph | https://cointelegraph.com/rss | 0.72 |
| DeFi/调查 | DL News | https://www.dlnews.com/arc/outboundfeeds/rss/ | 0.80 |
| BTC 专项 | Bitcoin Magazine | https://bitcoinmagazine.com/feed | 0.70 |
| 研究/链上 | Glassnode Insights | https://insights.glassnode.com/rss/ | 0.85 |
| 研究/市场结构 | Coin Metrics | https://coinmetrics.substack.com/feed | 0.82 |
| 研究/衍生品 | Deribit Insights | https://insights.deribit.com/feed/ | 0.78 |
| 研究/协议 | Messari | https://messari.io/rss | 0.80 |

说明：

- 全部源均为 `linked-summary-only`、`redistribution_allowed=false`、`30d-metadata-and-summary`、`en`。
- RSS provider 只存标题与短摘要，不存全文；拒绝 redirect、限大小/超时、ETag/Last-Modified 条件请求。
- 这些源在快讯页归为"文章"类型；Agent/日报/trending 通过 `rss` alias 自动纳入。
- 单个源 403/超时会由健康检查标记为 DEGRADED，不影响其余源与 ChainCatcher 快讯。
- 新增源只需向 `config/rss_sources.yaml` 追加条目；上线后看管理端 data-sources 健康状态确认可达。

## 合规与安全边界

- 只持久化标题、最多 600 字符的短摘要、发布时间、关键词、分类、资产标签、原创标记和原文 URL；不保存 RSS `content:encoded` 或 REST `content` 全文。
- 所有外链必须是 HTTPS 且主机位于固定 ChainCatcher allowlist；拒绝跳转、私网地址、大响应、异常 JSON/XML 和超时请求。
- UI 始终展示来源并通过 `nofollow noopener noreferrer` 打开原文。
- 当前许可状态记录为 `linked-summary-only; enterprise terms review required`，`redistribution_allowed=false`。正式商业上线前，运营方必须与 ChainCatcher 确认企业 API、调用频率、商用展示、缓存期限、署名样式和删除要求。
- 快讯只进入研究上下文，不能直接创建订单；投资与风险判断必须引用原始来源并结合其他证据。

## 可靠性与容量

| 项目 | 目标/策略 |
| --- | --- |
| RSS 同步 | 默认 5 分钟，单实例、任务合并 |
| REST 回补 | 默认 15 分钟，`zh-CN,en`，每种语言最多 100 条 |
| 请求保护 | 10 秒超时、3 次指数退避、5 MB 上限、拒绝 redirect |
| 降级 | RSS 或部分语言失败为 `DEGRADED`；全部失败为 `ERROR` |
| 熔断 | 复用统一文档管道，连续失败 3 次后 15 分钟熔断 |
| 幂等 | provider + external ID、内容哈希和事件指纹三层去重 |
| 查询 | 1–50 条、最长 7 天、无总数扫描、时间+ID 游标分页 |
| 保留 | 默认 30 天，仅元数据和短摘要；合同更严格时取更短期限 |

已有 `/metrics`、`DataSource`、`ProviderSyncLog` 和后台数据源页面承担可观测性。生产告警至少覆盖：连续两次同步失败、距最后成功同步超过 15 分钟、429、响应超过大小上限、单次入库为零且源端有数据。

## API 与前端

`GET /api/news` 需要登录并校验 RSS 数据权限，支持：

- `kind=flash|article|all`
- `source=chaincatcher|rss|all`
- `language=zh|en`
- `symbol=BTC`、`q=keyword`
- `hours=1..168`、`limit=1..50`、`cursor=...`

响应只包含可展示字段和数据状态，使用私有短缓存，避免浏览器直接访问上游 API。前端每分钟取第一页并与现有列表按 ID 合并，后台标签页不轮询。

英文用户在 REST 首次回补完成前可能只有中文 RSS。若某组英文筛选完全无结果，API 会临时返回其他语言并设置 `meta.language_fallback=true`，前端明确提示；一旦英文数据可用便自动恢复严格英文过滤。

## 上线步骤

1. 在测试环境启用 worker，手动同步 `chaincatcher`，核对中文/英文、快讯/文章分类、原文链接和去重。
2. 与 ChainCatcher 完成商用条款确认；如要求不同，调整 `license_status`、保留期限、调用频率和 UI 署名。
3. 运行后端测试、Web typecheck/lint/build，并对 `/zh/news`、`/en/news` 做移动端和桌面端验收。
4. 灰度 10% 用户 24 小时，观察 429、流量、延迟和零入库；再全量开放。
5. 若上游异常，可将 `CHAINCATCHER_SYNC_ENABLED=false`，其他 RSS、Agent 和日报继续工作。

## 配置

```dotenv
CHAINCATCHER_SYNC_ENABLED=true
CHAINCATCHER_RSS_URL=https://www.chaincatcher.com/rss/clist
CHAINCATCHER_API_BASE_URL=https://api.chaincatcher.com/v1/open-api
CHAINCATCHER_LANGUAGES=zh-CN,en,ja,ko
CHAINCATCHER_SYNC_INTERVAL_MINUTES=5
CHAINCATCHER_API_REFRESH_MINUTES=15
```
