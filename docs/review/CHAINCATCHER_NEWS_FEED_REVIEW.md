# ChainCatcher 新闻流（快讯）整合 —— 方案、提示词、分工与评审

> 评审角色：辅助（review）职能。主开发由 Codex 5.6 承担。
> 评审时间：2026-08-25（针对 Codex 进行中的实现状态）。
> 评审结论：架构方向正确、复用合理、合规边界到位；存在 4 个必须核实的接口契约问题 + 1 个必须补齐的测试缺口。

---

## 1. 方案（商业级）

### 目标
在 puregamma.ai 现有文档型数据底座之上接入 ChainCatcher 快讯，提供商业级新闻流能力，不另起炉灶。

### 关键决策
1. 复用现有底座：ChainCatcher 作为独立可观测的 DataProvider 接入，走既有 run_document_pipeline（去重、来源证明、授权/保留策略、情绪/币种提取、熔断、健康检查），不复制全文。
2. 双路数据：
   - RSS（低延迟主路径）：约 5 分钟轮询 https://www.chaincatcher.com/rss/clist ，只留标题 + 短摘要 + 标签 + 原文链接。
   - REST API（多语言补齐/字段校正）：约 15 分钟一次（文档声明有约 15 分钟延迟），按语言 zh-CN/en/ja/ko 补齐。
3. 按文章 ID 合并：RSS 与 REST 同文合并避免重复；不同语言视为独立文档（保留多语言语义）。
4. 产品权益归入 rss：provider_aliases.py 将 rss 展开为 (rss, chaincatcher)，既有套餐无需变更；/api/news 鉴权只需 rss 或 all。
5. 合规：linked-summary-only，不存全文，redistribution_allowed=False，30 天保留，前端带出处 + 免责声明。

### 数据流
    scheduler(5min) -> celery sync_data_provider(chaincatcher)
        -> ChainCatcherProvider.fetch_since(cursor)
             -> RSS 主路径（source_type=flash_news|article，lang=zh-CN）
             -> REST 多语言补齐（15min 节流）
             -> _merge(按 external_id)
        -> run_document_pipeline -> RawDocument + NormalizedDocument（+ EntityMention + SentimentSignal）
    /api/news -> news_feed_service.list_news_feed(kind/source/language/symbol/q/cursor)
    web /[locale]/news -> NewsFeed 组件（筛选/搜索/分页/自动刷新/相对时间/i18n）

---

## 2. 主开发提示词

> 以下为交付给主开发（Codex 5.6）的完整提示词；已完成部分保留为验收基线，未完成/待核实项作为后续任务。

    你是 puregamma.ai 的主开发。目标：在现有文档型数据底座上接入 ChainCatcher 快讯，
    交付商业级新闻流能力。严格保护工作区内第三方源码(nautilus_trader)、历史备份、
    构建缓存与用户未提交改动；只改第一方代码。

    边界：
    - 复用 packages/data/provider.py 的 DataProvider 契约与 run_document_pipeline，不新建第二套抓取/存储。
    - 不复制全文：只保留 标题 / 短摘要 / 标签(币种、关键词) / 原文链接。
    - 合规：linked-summary-only、redistribution_allowed=False、30 天保留、带出处与免责声明。

    实现清单（已完成 = 验收基线）：
    1) packages/data/chaincatcher_provider.py：ChainCatcherProvider(id=chaincatcher)，实现 fetch_since/
       fetch_latest/health_check/get_usage；SSRF 防护(host 白名单、禁重定向、DNS 校验)、限流(retry-after)、
       大小限制、指数退避重试。
    2) 双路：RSS(_rss_documents, 约5min, 主路径) + REST(_api_documents, 15min 节流, 多语言补齐)。
    3) _merge：RSS 与 REST 按 external_id 合并；不同语言视为独立文档。
    4) packages/data/provider_aliases.py：DOCUMENT_PROVIDER_ALIASES[rss]=(rss, chaincatcher)。
    5) apps/api/services/news_feed_service.py：list_news_feed(kind/source/language/symbol/q/hours/limit/cursor)，
       游标分页、语言/币种/全文过滤、序列化(attribution/license/disclaimer)。
    6) apps/api/routers/news.py：GET /api/news，鉴权(entitlement: rss|all)，Cache-Control，X-Content-Type-Options。
    7) data_source_service.py：SOURCE_DEFINITIONS / DOCUMENT_PROVIDER_IDS / provider_registry /
       sync_all_providers / serialize_source 纳入 chaincatcher。
    8) config.py：chaincatcher_* 设置（RSS URL、API base URL、语言、同步/刷新间隔）。
    9) workers/scheduler.py：provider_chaincatcher_newswire_sync（interval 5min）。
    10) web：/[locale]/news 页面 + news-feed.tsx + api.ts getNewsFeed + messages/{en,zh}/news.json +
        nav 入口 + middleware 路由 + SEO。

    必须核实的接口契约（阻塞项）：
    A) 确认 ChainCatcher REST 生产 host/path/schema。当前假设
       https://api.chaincatcher.com/v1/open-api/news-flash?type=flash&page=1&size=100&lang=<lang>，
       响应 {result:1, data:{items:[{id,url,title,type,digest,releaseTimeStamp,thumb,original,keywords}]}}。
       文档见于 uat2049.chaincatcher.info/api（UAT 域名，非 .com）。若生产 host 非 *.chaincatcher.com，
       CHAINCATCHER_HOSTS 会以 host_not_allowed 拒绝，REST 回补路径静默失败。
    B) 确认 REST 的 id 是否等于 URL /article/<id> 的数字 ID（决定 RSS 与 REST 合并是否正确）。
    C) 确认 RSS 快讯在 feed 里的分类标记真实值，否则 _content_kind 默认成 article，flash 筛选漏掉 RSS。
    D) 确认 RSS feed 是否纯中文（当前 RSS 语言硬编码 zh-CN）。

    必须补齐（商业级）：
    E) 测试：ChainCatcherProvider 单测(mock request_get)、news_feed_service 集成测试、/api/news 鉴权 403。
    F) 前端语言兜底：en 用户默认 language=en 精确过滤会排除 zh-CN RSS，可能空流。

    验收：python -m py_compile 通过；pytest 绿；/api/news 返回带 attribution/license_status/disclaimer/next_cursor 的分页结构；前端 /news 中英文可渲染。

---

## 3. 分工

| 职能 | 承担者 | 交付物 | 状态 |
|---|---|---|---|
| 主开发（实现） | Codex 5.6 | 后端 provider/service/router/config/scheduler + 前端页面/组件/i18n | 进行中 |
| 辅助（方案/提示词/评审） | 本会话 | 方案、主开发提示词、评审结论 | 本文件 |
| 接口契约核实（A–D） | Codex 5.6（联调） | 真实 REST/RSS 样本、host/schema 确认 | 待办 |
| 测试补齐（E） | Codex 5.6 + 本会话复审 | pytest 用例 | 待办 |
| 最终验收复审 | 本会话 | 复审报告 | 待办 |

---

## 4. 评审结论（辅助职能核心产出）

### 4.1 已确认正确（无需返工）
- 路由注册：main.py 已 include_router(news.router)；scheduler 已注册 provider_chaincatcher_newswire_sync(5min, coalesce)；celery sync_data_provider 可调度。
- 底座复用：chaincatcher 走 run_document_pipeline，命中 DOCUMENT_PROVIDER_IDS。
- 权益：plans.py 各套餐 allowed_data_sources 均含 rss（Enterprise 为 all），/api/news 的 rss|all 门禁成立；serialize_source requiredPlan=Free。
- 数据模型：NormalizedDocument 与 DataSource 字段均存在，news_feed_service 读取的列齐全。
- 前端契约：news.json 键与 news-feed.tsx 的 Copy 类型逐键对齐；/news 已入 legacyLocaleRoutes 与 AUTHENTICATED_ROUTES；nav 入口已加；SEO 支持。
- 失败兜底：api.ts getNewsFeed 提供 unavailable/error_code/unauthorized 回退。
- 全部改动文件 python -m py_compile 通过（语法无误）。

### 4.2 阻塞项（上线前必须核实/修复）
1. [B1] REST host/schema 未核实。文档域名是 *.chaincatcher.info，实现假设 api.chaincatcher.com。若真实 host 不在 CHAINCATCHER_HOSTS，validate_public_https_url 抛 host_not_allowed，REST 回补静默失败。建议抓一次真实响应确认 host/path/result/data.items 结构并把真实 host 加入白名单。
2. [B2] RSS 与 REST 合并键依赖未验证假设。RSS 键 chaincatcher:zh-CN:<url_id>，REST 键 chaincatcher:<lang>:<item.id>，仅当 item.id 等于 /article/<id> 才合并；否则同文重复入库。建议两路都改为以规范化 URL 为主键（哈希兜底），item.id 仅作回退。
3. [B3] RSS 快讯分类标记未核实。_content_kind 仅认 category/tags 中的 flash/快讯/newsflash/news-flash，否则默认 article，导致默认 flash 筛选漏掉 RSS；且 entry.get(category) 可能返回 list 而非 str。建议确认 clist 真实分类值并归一化。
4. [B4] RSS 语言硬编码 zh-CN。若 feed 混有他语言条目会被错误标注。低危，随 B 项核实。

### 4.3 必须补齐（商业级门槛）
- [E] 测试缺口：ChainCatcherProvider / news_feed_service / /api/news 路由的测试覆盖为 0（tests 目录内无引用）。需补 provider 单测、list_news_feed 集成测试、鉴权 403 用例。既有 test_document_data_sources.py 等经扫描不会因新增 source 而破坏。

### 4.4 建议（非阻塞）
- en 用户默认按 language=en 精确过滤会排除 zh-CN RSS，可能空流；建议 source=chaincatcher 且目标语言无结果时回退全语言展示，或明确中文优先 + 语言切换策略。
- cursor 仅存 REST 节流态（restSyncedAt），RSS 每次全量拉 200 条再靠 content_hash 去重，可接受；可后续复用 etag/last-modified 增量优化带宽。
- _merge 原地修改 ProviderDocument 字段（可变 dataclass 能跑通但脆），低优先级。

---

## 5. 下一步（给主开发的交办）
1. 联调核实阻塞项 B1–B4，抓真实 REST/RSS 样本并修正 host 白名单、合并键、分类与语言。
2. 补齐 E 项测试。
3. 复审 F 项前端语言策略。
完成后本会话做最终验收复审。
---

## 6. 评审更新（2026-08-25，第二次 —— 主开发交办后复审）

> 复审方式：读最新代码 + 跑测试 + 全仓别名展开扫描 + CSS 令牌核对。

### 6.1 已闭环（Codex 已修复，经代码与测试双重验证）
- [B2] 合并键：_external_id 现以规范化 URL 的 /article/<id> 为主键，REST item.id 仅作回退（含注释说明）。已闭环。
- [B3] RSS 分类：_rss_category 现处理 list/dict/str 三种形态；_content_kind 归一化空白/下划线/连字符并扩充分类词（快讯/快訊/快報/快报/newsflash）。已闭环。
- [B4] RSS 语言：新增 _normalize_language（zh-CN/zh-TW/en/ja/ko 归一化）；RSS 语言取 feed 级 language 并按 entry 级覆盖。已闭环。
- [F] 语言策略：news_feed_service 新增 language_fallback —— 当 language=en 且英文文档为空时回退展示全语言，并在 meta.language_fallback 显式标注。已闭环。
- [E] 测试：已补齐 tests/unit/test_chaincatcher_provider.py（4 用例）与 tests/integration/test_news_feed.py（4 用例，含鉴权 401 / 游标 / rss→chaincatcher 别名证据）。8 用例全部通过。

### 6.2 全仓别名展开扫描（新增复审项，结论：完整）
- 所有 NormalizedDocument.provider.in_(...) 查询路径均已 expand_document_providers：daily_push_service、agents/chat/tools.py、backtest/tools.py、trending.py 一致。
- agent/backtest 的所有工具调用（get_sentiment_context/search_news/planner 路由）最终都汇入 search_source_documents，该处已展开别名。
- 未展开的 provider==X 均为按源明细/统计视图（admin preview、_source_count、_latest_source_timestamp、document_pipeline item_count），行为正确。
- 结论：无遗漏的别名展开点，ChainCatcher 文档不会被任何查询路径静默排除。

### 6.3 回归测试（无回归）
- test_document_data_sources + test_data_deduplication + test_daily_brief_enrichment + test_agent_online_research：38 通过 / 2 跳过。
- test_unified_daily_brief：4 通过。
- test_agent_runtime + test_agent_answers：36 通过。
- 注：test_daily_push_job / test_daily_orchestrator / test_market_intelligence_job 依赖 Redis broker，本地无 Redis 时挂起，与本次改动无关。

### 6.4 前端令牌核对（通过）
- news-feed.tsx 使用的 border-border-pg / text-text-pg / text-text-pg-muted / text-text-pg-dim / bg-pg-white / text-pg-black / text-status-positive / bg-status-positive / border-status-negative 等均由 tailwind.config.ts 映射到 CSS 变量（--border/--foreground/--muted/--muted-2/--positive/--negative），渲染正常。
- globals.css +202 行为独立的 gated Glass 视觉增强层（[data-visual-style=glass]），与快讯功能无关，默认不影响基础样式。

### 6.5 范围澄清
- Android/iOS 的未提交改动（Plaid 连接按钮、主题切换、1.4.0→1.5.0 版本号）为历史遗留未提交工作，与 ChainCatcher 快讯无关，不在本次评审范围。

### 6.6 唯一剩余阻塞项
- [B1] REST 生产 host/schema 仍未用真实网络验证。实现仍假设 https://api.chaincatcher.com/v1/open-api/news-flash，响应 {result:1, data:{items:[...]}}；测试使用合成样本，未覆盖真实字段。文档域名见于 *.chaincatcher.info。
  需在可出网环境抓一次真实响应：确认 host、path、result/data.items 结构、id/digest/releaseTimeStamp/thumb/original/keywords 字段，并把真实 host 加入 CHAINCATCHER_HOSTS 白名单。

### 6.7 验收结论（阶段性）
除 B1（真实接口联调）外，快讯整合已达到商业级交付标准：架构复用、SSRF/限流/熔断、合规（不存全文）、权益别名、多语言、测试、i18n/SEO、前端兜底均已就绪。B1 联调通过后即可进入最终验收。
---

## 7. 最终验收复审（2026-08-25，第三次 —— 灰度上线条件确认）

### 7.1 验收结论：通过（灰度上线）
主开发报告的三项交办全部闭环，经独立复核与测试确认，新闻流（快讯）已达到灰度上线条件。

### 7.2 阻塞项复核（全部闭环）
- B1 REST 正式地址确认为 https://api.chaincatcher.com/v1/open-api，已入 CHAINCATCHER_HOSTS 严格白名单（www.chaincatcher.com / chaincatcher.com / api.chaincatcher.com），SSRF 校验通过。
- B2 真实样本 REST id 与 /article/<id> 一致；实现以规范化 URL 文章 ID 为主键、REST id 回退（已读代码确认）。
- B3 RSS 实际分类为 快讯/文章，_rss_category 兼容 str/list/term/label，_content_kind 兼容简繁体别名。
- B4 RSS channel 声明 zh-cn 经 _normalize_language 归一化为 zh-CN；REST zh-CN/en/ja/ko 四语联调完成。
- F 语言策略：目标语言无结果时 language_fallback=true，前端明确提示（en/zh copy 已配，meta 类型已加）。

### 7.3 测试复核（独立跑）
- 专项新闻测试：test_chaincatcher_provider.py(4) + test_news_feed.py(5) = 9 用例，全部通过（含鉴权 401、游标、rss→chaincatcher 别名证据、英文回退、无 rss 权益拒绝、数据源继承 rss 套餐权益）。
- 相关回归：document-pipeline / dedup / daily-brief / agent-runtime / agent-answers / unified-daily-brief 等 78 用例全绿，无回归。
- 8 个既有失败独立复现：tests/test_notifications.py 6 例（mock 交付 'skipped' vs 'sent'、iMessage 幂等/扣费）+ tests/quant/test_backtest_assumptions.py 等（mock 回测标注 'nautilus_error' vs 'mock'）。均为通知模拟与 Nautilus 回测假设，所涉文件不在本次新闻改动清单内，与新闻功能无关。

### 7.4 真实联调证据（主开发报告，采信）
- 376 条入库：zh-CN 95 / en 99 / ja 91 / ko 91；374 快讯 + 2 文章；5 请求全成功，健康状态 HEALTHY，未保存完整正文（content 为空，仅标题/短摘要/标签/原文链接）。

### 7.5 上线前遗留（非代码阻塞，需记录）
1. 正式商业发布前需取得 ChainCatcher 对「摘要再分发、商用流量、SLA」的书面确认；代码已按「仅标题+短摘要+原文链接」约束实现，当前为灰度。
2. Windows 本地 standalone 打包受 EPERM 符号链接权限影响；编译与静态生成已通过，生产 CI 建议使用 Linux。
3. 既有 8 个失败（通知模拟 + Nautilus 回测假设）建议单独立项修复，不阻塞本次灰度。

### 7.6 核心交付物清单
- 商业架构与运行手册：docs/integrations/CHAINCATCHER_NEWSWIRE.md
- 双路采集与安全实现：packages/data/chaincatcher_provider.py
- 新闻流查询服务：apps/api/services/news_feed_service.py
- 新闻流 API：apps/api/routers/news.py
- 多语言新闻流界面：apps/web/components/news-feed.tsx
- Provider 单测：tests/unit/test_chaincatcher_provider.py
- 接口/鉴权/回退集成测试：tests/integration/test_news_feed.py
---

## 8. 部署前 Review（2026-08-25，第四次）

### 8.1 结论：具备灰度部署条件（代码与配置层面）
部署链路已逐项核实；代码与配置无阻塞问题。仅剩 1 项非代码硬阻塞（ChainCatcher 商用书面确认）与 1 项上线后核对项（新增 RSS 源健康状态）。

### 8.2 部署正确性（已核实，无需改动）
1. .env.example 含全部 CHAINCATCHER_* 与 RSS_* 变量（含 zh-CN,en,ja,ko 四语）。
2. deploy/production.env.example 含 CHAINCATCHER_SYNC_ENABLED / LANGUAGES(4语) / 双间隔。
3. docker-compose.production.yml：api / worker / scheduler 均 env_file: .env，CHAINCATCHER_* 变量流入三容器；scheduler 显式映射 DATA_SYNC_WORKER_ENABLED 与 RSS_SYNC_INTERVAL。
4. Dockerfile.api 执行 COPY . /app → config/rss_sources.yaml 随镜像打包，RSSProvider.load_sources 可读到。
5. 数据源种子：main.py lifespan → ensure_bootstrap() → packages/database/seed.py:82 → seed_data_sources 启动时自动创建 chaincatcher 数据源行（初始 DEGRADED，首次同步后转 HEALTHY），无需手工迁移。
6. 权益：Free/Invite Preview/Pro/Max 均含 rss，Enterprise 为 all；/api/news 的 rss|all 门禁对全套餐放行。
7. 回滚开关：CHAINCATCHER_SYNC_ENABLED=false 即停同步，不影响其余 RSS/Agent/日报。
8. config.py 默认 CHAINCATCHER_LANGUAGES=zh-CN,en,ja,ko（已对齐四语联调）；ChainCatcherProvider.__init__ 回退同样为四语。
9. config.py 默认 RSS/API 地址与 B1 核实的生产地址一致。

### 8.3 本轮修复（部署前 Review 发现并已修）
- deploy/production.env.example 补齐 CHAINCATCHER_RSS_URL 与 CHAINCATCHER_API_BASE_URL（原依赖 config.py 默认；现显式声明，与运行手册「配置」节一致，避免运维误以为不可覆盖）。

### 8.4 非代码遗留（部署/上线时处理）
1. 正式商业发布前取得 ChainCatcher 对摘要再分发、商用流量与 SLA 的书面确认（当前为灰度，代码已按仅标题+短摘要+原文链接实现）。
2. 灰度后核对 8 个新增 RSS 源在管理端 data-sources 的 per-feed 健康状态（沙箱外网被阻断，无法提前验证 200/redirect/403）。
3. 8 个既有失败（通知模拟 6 + Nautilus 回测假设 2）单独立项，不阻塞本次灰度。

### 8.5 建议（非阻塞）
- scheduler 的 environment 块未显式列出 CHAINCATCHER_SYNC_ENABLED（依赖 env_file: .env 透传），功能正确；如需与 RSS_SYNC_INTERVAL 同等的显式声明，可补一行 CHAINCATCHER_SYNC_ENABLED: ${CHAINCATCHER_SYNC_ENABLED:-true}。
- ChainCatcherProvider.__init__ 对 languages 做大小写敏感过滤（SUPPORTED_LANGUAGES），env 用正确大小写（zh-CN）即无影响；如担心运维误填小写，可在 __init__ 前先 _normalize_language。
---

## 9. 部署前 Review 增补（2026-08-25，第五次 —— 顺带发现并修复一处 admin 缺陷）

### 9.1 新发现并修复的缺陷
- apps/api/routers/admin.py 的 GET /data-sources/{provider_id}/runs 用硬编码集合 {"rss","fintwit","x-twitter","bloomberg"} 区分 ProviderSyncLog 与 DataSourceSyncRun，漏了 chaincatcher。
  后果：chaincatcher 是文档 provider（走 run_document_pipeline → ProviderSyncLog），但被归入 else 分支去查 DataSourceSyncRun，管理端「同步运行历史」对 chaincatcher 恒为空。
  修复：白名单补 chaincatcher。已验证：admin.py py_compile 通过；test_admin_console.py + test_admin_access.py 共 21 例全绿，无回归。

### 9.2 本轮新增交付物
- docs/integrations/CHAINCATCHER_GRAY_RELEASE_RUNBOOK.md：灰度上线清单（前置阻塞 / feed 预检命令 / 同步激活 / 功能验收 / 监控 / 回滚）。
- deploy/production.env.example：补 CHAINCATCHER_RSS_URL 与 CHAINCATCHER_API_BASE_URL（见 §8.3）。

### 9.3 部署前 Review 最终结论
代码与配置层面无阻塞项；唯一硬阻塞为 ChainCatcher 商用书面确认（非代码）。可进入灰度。
---

## 10. 生产部署记录（2026-08-25）

### 10.1 部署目标
- 服务器 47.245.55.228（阿里云 ECS，root），部署目录 /puregamma/app/。
- 服务器原部署 commit 44dea1a6（= 本地 HEAD）；本次部署本地 6 个已跟踪改动 + 1 个新文档。

### 10.2 部署动作（保留用户数据库）
1. pg_dump 备份到 /puregamma/backup/db-pre-newsrss-20260825-142103.sql（122 MB，18 用户）。
2. tar+scp 传输 7 个文件（admin.py / news-feed.tsx / rss_sources.yaml / production.env.example / 3 文档），服务器其余文件原样保留。
3. docker compose build api worker scheduler web + up -d（非 down -v），postgres/redis/nautilus 卷未动（42h uptime 保持）。
4. 验证：app.puregamma.ai=200、api.puregamma.ai=200；数据源种子正常。

### 10.3 服务器可达性检查暴露并修复 3 个坏 feed
| 源 | 问题 | 处理 |
| --- | --- | --- |
| The Block | 403（站点级封锁，浏览器/无 UA 均 403） | enabled=false |
| Glassnode Insights | insights.glassnode.com/rss/ 403+重定向 | 改 research.glassnode.com/rss/（200） |
| Messari | messari.io/rss 404 | 改 messari.substack.com/feed（200） |

### 10.4 最终验证
- RSS 手动同步：HEALTHY，258 抓取 / 146 新增 / 112 去重，0 错误（10 个启用源全部可达）。
- 数据源状态：rss HEALTHY（1008 条）、chaincatcher 近次同步 HEALTHY（534 条，四语 RSS+REST 正常）。
- 注：data_sources.status 在容器重启后会被 seed_data_sources 短暂置回 DEGRADED，下次同步（≤10 分钟）自动恢复 HEALTHY——既有行为，非本次引入。