"use client";

import Link from "next/link";
import {
  ArrowRight,
  Check,
  CircleDollarSign,
  Code2,
  Copy,
  ExternalLink,
  KeyRound,
  Layers3,
  LockKeyhole,
  ServerCog,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  WalletCards,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { PageHeader } from "@/components/puregamma";
import { getGatewayCatalog, type GatewayCatalog, type GatewayCatalogModel, type GatewayCatalogPrice } from "@/lib/api";
import { catalogAvailabilityLabel, catalogProviderLabel } from "@/lib/model-catalog";
import { getMessageNamespace } from "@/lib/translations";
import { withLocale } from "@/i18n/routing";

const baseUrl = "https://api.puregamma.ai/v1";
const docsBaseUrl = (process.env.NEXT_PUBLIC_DOCS_URL || "https://puregamma-ai.gitbook.io/puregamma-ai").replace(/\/+$/, "");

const modelNarratives = {
  "deepseek-flash": {
    en: {
      title: "DeepSeek V4.1 Flash",
      badge: "Default",
      summary: "Low-latency chat, batch workloads, and value-oriented production paths.",
      detail: "DeepSeek's current Flash generation, released 10 September 2026. It supersedes the previous V4 Flash build on quality while costing less, and it is the default route for PureGamma chat, agent, report and research workloads. Thinking mode is available but disabled by default on these paths.",
      bestFor: "Fast chat · batch jobs · cost-sensitive workloads",
    },
    zh: {
      title: "DeepSeek V4.1 Flash",
      badge: "默认",
      summary: "低延迟对话、批量任务和性价比优先场景。",
      detail: "DeepSeek 于 2026 年 9 月 10 日发布的当前 Flash 代模型，能力超过上一代 V4 Flash 且价格更低，是 PureGamma 对话、Agent、报告与研究任务的默认路由。支持思考模式，但上述路径默认关闭。",
      bestFor: "快速对话 · 批量任务 · 成本敏感工作负载",
    },
  },
  "deepseek-v4-flash": {
    en: {
      title: "DeepSeek V4.1 Flash (legacy id)",
      badge: "Compatibility alias",
      summary: "Retained so existing integrations keep working without a code change.",
      detail: "DeepSeek retired the deepseek-v4-flash model and routes this id to DeepSeek V4.1 Flash. Requests and billing are identical to deepseek-flash; new integrations should use deepseek-flash.",
      bestFor: "Existing integrations · migration window",
    },
    zh: {
      title: "DeepSeek V4.1 Flash（旧 ID）",
      badge: "兼容别名",
      summary: "保留旧 ID，已有集成无需改代码即可继续调用。",
      detail: "DeepSeek 已下线 deepseek-v4-flash 模型，该 ID 会被路由到 DeepSeek V4.1 Flash。请求行为与计费同 deepseek-flash 完全一致；新接入请直接使用 deepseek-flash。",
      bestFor: "已有集成 · 迁移过渡期",
    },
  },
  "deepseek-v4-pro": {
    en: {
      title: "DeepSeek V4 Pro",
      badge: "Being retired",
      summary: "Scheduled to route to V4.1 Flash from 14 September 2026, 12:00 Beijing time.",
      detail: "DeepSeek announced the orderly retirement of V4 Pro because V4.1 Flash outperforms it on their published benchmarks. After the announced cut-over this id is served by V4.1 Flash and billed at Flash prices. Use deepseek-flash directly for new work.",
      bestFor: "Migration reference only",
    },
    zh: {
      title: "DeepSeek V4 Pro",
      badge: "即将下线",
      summary: "自北京时间 2026 年 9 月 14 日 12:00 起路由至 V4.1 Flash。",
      detail: "DeepSeek 因 V4.1 Flash 在官方基准上全面超越 V4 Pro，已公告有序下线 V4 Pro。切换后该 ID 由 V4.1 Flash 提供服务并按 Flash 价格计费。新任务请直接使用 deepseek-flash。",
      bestFor: "仅作迁移参考",
    },
  },
  "kimi-k3-max": {
    en: {
      title: "Kimi K3 Max",
      badge: "Long context",
      summary: "Long documents and multi-step tool workflows with a 1M-token context window.",
      detail: "PureGamma exposes the compatibility id kimi-k3-max and routes it to Moonshot's official kimi-k3 model. It is designed for long-horizon coding, knowledge work, and tool-driven workflows.",
      bestFor: "Long documents · agent workflows · knowledge work",
    },
    zh: {
      title: "Kimi K3 Max",
      badge: "长上下文",
      summary: "长文档、复杂工具工作流和 1M 上下文任务。",
      detail: "PureGamma 对外兼容 ID 为 kimi-k3-max，实际调用 Moonshot 官方 kimi-k3。适合长程代码、知识工作与多步骤工具工作流。",
      bestFor: "长文档 · Agent 工作流 · 知识工作",
    },
  },
  "glm-5.2": {
    en: {
      title: "GLM 5.2",
      badge: "General",
      summary: "General Chinese/English tasks and tool calling with 1M context.",
      detail: "A general-purpose option for Chinese and English production tasks, structured outputs, and tool-driven workflows. Its official SKU is China-region CNY, so billing activation requires an approved currency policy.",
      bestFor: "Chinese/English · structured output · tools",
    },
    zh: {
      title: "GLM 5.2",
      badge: "通用",
      summary: "中英文通用任务与工具调用，支持 1M 上下文。",
      detail: "适合中英文生产任务、结构化输出和工具工作流。其官方 SKU 为中国区人民币计价，因此在币种策略获批前不会作为可计费美元路由启用。",
      bestFor: "中英文 · 结构化输出 · 工具调用",
    },
  },
} as const;

type ModelId = keyof typeof modelNarratives;

const modelOrder: ModelId[] = [
  "deepseek-flash",
  "deepseek-v4-flash",
  "deepseek-v4-pro",
  "kimi-k3-max",
  "glm-5.2",
];

type Narrative = { title: string; badge: string; summary: string; detail: string; bestFor: string };

/**
 * Resolve display copy for a catalog model.
 *
 * The curated narratives above are editorial and can lag the catalog. Any model
 * the deployment starts serving must still be selectable and correctly labelled,
 * so a missing narrative falls back to the catalog's own `display_name` plus an
 * explicit "no reviewed summary" note instead of rendering blank fields.
 */
function narrativeFor(
  id: string,
  catalogModel: GatewayCatalogModel | undefined,
  zh: boolean,
  copy: ReturnType<typeof getMessageNamespace<"model-upgrade">>,
): Narrative {
  const curated = (modelNarratives as Record<string, { en: Narrative; zh: Narrative } | undefined>)[id];
  if (curated) return curated[zh ? "zh" : "en"];
  return {
    title: catalogModel?.display_name || id,
    badge: catalogModel?.provider_display_name || catalogModel?.provider || "",
    summary: copy.preview.catalogNoSummary,
    detail: copy.preview.catalogNoSummary,
    bestFor: "",
  };
}

function providerLabel(model: GatewayCatalogModel | undefined, id: string) {
  return catalogProviderLabel(model, id);
}

function availabilityLabel(
  model: GatewayCatalogModel,
  catalog: GatewayCatalog | null,
  zh: boolean,
) {
  return catalogAvailabilityLabel(model, catalog, zh);
}
type CodeLanguage = "curl" | "python" | "node";

function CopyButton({ value, label, copiedLabel }: { value: string; label: string; copiedLabel: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <button
      type="button"
      onClick={() => void copy()}
      className="inline-flex min-h-9 items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted transition hover:border-border-pg-strong hover:text-text-pg rounded-lg"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-status-positive" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? copiedLabel : label}
    </button>
  );
}

function CodeBlock({
  language,
  value,
  copyLabel,
  copiedLabel,
  compact = false,
}: {
  language: string;
  value: string;
  copyLabel: string;
  copiedLabel: string;
  compact?: boolean;
}) {
  return (
    <div className="overflow-hidden border border-border-pg bg-bg-app rounded-xl">
      <div className="flex items-center justify-between border-b border-border-pg px-3 py-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-pg-dim">{language}</span>
        <CopyButton value={value} label={copyLabel} copiedLabel={copiedLabel} />
      </div>
      <pre className={`touch-pan-x overflow-x-auto overscroll-x-contain ${compact ? "p-3 text-[11px] leading-5" : "p-3 sm:p-4 text-xs leading-6"} text-text-pg`}><code>{value}</code></pre>
    </div>
  );
}

function priceAmount(item: GatewayCatalogPrice | undefined, currency: string) {
  if (!item) return "—";
  const symbol = currency === "USD" ? "$" : currency === "CNY" ? "¥" : `${currency} `;
  return `${symbol}${item.amount}`;
}

function priceUnit(item: GatewayCatalogPrice | undefined, zh: boolean) {
  if (item?.unit === "per_million_tokens") return zh ? "/ 百万 tokens" : "/ 1M tokens";
  if (item?.unit === "per_unit") return zh ? "/ 单位" : "/ unit";
  return item?.unit || "";
}

function compactTokens(value: unknown) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric) || numeric <= 0) return "—";
  if (numeric >= 1_000_000) return `${numeric / 1_000_000}M`;
  if (numeric >= 1_000) return `${numeric / 1_000}K`;
  return String(numeric);
}

function supports(model: GatewayCatalogModel | undefined, capability: string) {
  return Boolean(model?.capabilities?.[capability]);
}

function pricingStatus(
  catalog: GatewayCatalog | null,
  model: GatewayCatalogModel | undefined,
  zh: boolean,
) {
  const pricing = model?.pricing;
  if (!catalog || catalog.unavailable) return zh ? "价格目录加载中" : "Loading price catalog";
  if (!catalog.gateway_enabled) return zh ? "网关待安全启用" : "Gateway pending activation";
  if (model?.availability === "available" && pricing?.status === "active") return zh ? "可用且价格已审核" : "Available · price approved";
  if (pricing?.status === "requires_currency_policy") return zh ? "人民币报价 · 币种策略待审核" : "CNY quote · currency policy pending";
  if (pricing?.status === "catalog_unapproved") return zh ? "官方目录报价 · 待审核" : "Official catalog quote · pending approval";
  return zh ? "模型与价格待审核" : "Model and pricing pending review";
}

function PriceCompare({
  label,
  official,
  final,
  currency,
  zh,
}: {
  label: string;
  official: GatewayCatalogPrice | undefined;
  final: GatewayCatalogPrice | undefined;
  currency: string;
  zh: boolean;
}) {
  const officialLabel = zh ? "官方价格" : "Official price";
  const finalLabel = zh ? "PureGamma 价格" : "PureGamma price";
  return (
    <div className="border border-border-pg bg-bg-panel-muted p-3 rounded-lg">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{label}</div>
      {official && final ? (
        <>
          <div className="mt-3 grid min-w-0 grid-cols-2 items-end gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:gap-2">
            <div className="min-w-0">
              <div className="break-words text-[9px] font-semibold uppercase leading-3 tracking-[0.12em] text-text-pg-dim">{officialLabel}</div>
              <div className="mt-1 font-mono text-sm text-text-pg">{priceAmount(official, currency)}</div>
            </div>
            <ArrowRight className="mb-0.5 hidden h-3.5 w-3.5 text-text-pg-dim sm:block" />
            <div className="min-w-0 text-right">
              <div className="break-words text-[9px] font-semibold uppercase leading-3 tracking-[0.12em] text-text-pg-dim">{finalLabel}</div>
              <div className="mt-1 font-mono text-sm font-semibold text-text-pg">{priceAmount(final, currency)}</div>
            </div>
          </div>
          <div className="mt-1 text-[11px] text-text-pg-muted">{priceUnit(official, zh)}</div>
        </>
      ) : <div className="mt-3 text-sm text-text-pg-dim">{zh ? "待审核" : "Pending review"}</div>}
    </div>
  );
}

/** Native product documentation and model selector for the OpenAI-compatible Gateway. */
export function ApiDocsEmbed() {
  const locale = useLocale();
  const zh = locale === "zh";
  const modelCopy = getMessageNamespace(locale, "model-upgrade");
  const docsUrl = zh ? `${docsBaseUrl}/api-gateway` : `${docsBaseUrl}/api-gateway-en`;
  const [catalog, setCatalog] = useState<GatewayCatalog | null>(null);
  const [selectedId, setSelectedId] = useState<string>("deepseek-flash");
  const [language, setLanguage] = useState<CodeLanguage>("curl");

  useEffect(() => {
    let active = true;
    void getGatewayCatalog(locale).then((next) => {
      if (active) setCatalog(next);
    });
    return () => { active = false; };
  }, [locale]);

  const catalogModels = catalog?.models ?? [];
  const selectedCatalog = catalogModels.find((model) => model.id === selectedId);
  const narrative = narrativeFor(selectedId, selectedCatalog, zh, modelCopy);
  const selectedName = narrative.title;
  const currency = selectedCatalog?.pricing?.currency || "USD";  const pricingHeading = zh ? "价格明细" : "Pricing details";
  const priceComparisonDescription = zh
    ? "目录报价仅供参考，不能替代可计费价格。"
    : "Catalog quotes are for reference and do not replace billable prices.";
  const officialPriceLabel = zh ? "官方价格" : "Official price";
  const finalPriceLabel = zh ? "PureGamma 价格" : "PureGamma price";
  const official = selectedCatalog?.pricing?.official || {};
  const final = selectedCatalog?.pricing?.final || {};
  // Availability is read from the live catalog, never asserted in copy: the
  // "live" wording only appears once the Gateway really serves the model.
  const selectedAvailabilityLabel = selectedCatalog
    ? {
        available: zh ? "已上线" : "Live",
        pending_approval: zh ? "预览中 · 待价格审批" : "Preview · price pending approval",
        provider_disabled: zh ? "暂不可用 · 渠道已停用" : "Unavailable · provider disabled",
        setup_required: zh ? "配置中" : "Setup required",
      }[selectedCatalog.availability]
    : null;
  const availabilityIsLive = selectedCatalog?.availability === "available" && Boolean(catalog?.gateway_enabled);

  // Jev has no messages, no stream and no tool calls. Copying the chat
  // snippets for it would hand a customer a request that cannot succeed, so
  // the template follows the capability the catalog actually advertises.
  const isSystemOne = selectedCatalog?.capabilities?.system_one === true;
  const systemOneQuestion = `{
      "is_healthy": {"type": "noul", "instructions": "Does this indicate a healthy deploy?"},
      "severity": {"type": "score", "instructions": "How serious is the failure?", "criteria": ["Cosmetic", "Degraded", "Outage"]}
    }`;

  const snippets = {
    env: `# Server only — never expose this value to a browser or mobile app
PUREGAMMA_API_KEY=sk-pg-...
PUREGAMMA_BASE_URL=${baseUrl}
PUREGAMMA_MODEL=${selectedId}`,
    curl: isSystemOne
      ? `curl -sS $PUREGAMMA_BASE_URL/systemone \\
  -H "Authorization: Bearer $PUREGAMMA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${selectedId}",
    "state": "The build passed and every canary is green.",
    "questions": ${systemOneQuestion}
  }'`
      : `curl -sS $PUREGAMMA_BASE_URL/chat/completions \\
  -H "Authorization: Bearer $PUREGAMMA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${selectedId}",
    "messages": [{"role": "user", "content": "Hello from PureGamma."}]
  }'`,
    python: isSystemOne
      ? `import os
import httpx

response = httpx.post(
    f"{os.environ['PUREGAMMA_BASE_URL']}/systemone",
    headers={"Authorization": f"Bearer {os.environ['PUREGAMMA_API_KEY']}"},
    json={
        "model": "${selectedId}",
        "state": "The build passed and every canary is green.",
        "questions": ${systemOneQuestion},
    },
)
# Typed answers, not text: branch on these directly.
print(response.json()["answers"]["is_healthy"]["noul"])`
      : `from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["PUREGAMMA_API_KEY"],
    base_url=os.environ["PUREGAMMA_BASE_URL"],
)

response = client.chat.completions.create(
    model="${selectedId}",
    messages=[{"role": "user", "content": "Hello from PureGamma."}],
)
print(response.choices[0].message.content)`,
    node: isSystemOne
      ? `const response = await fetch(\`\${process.env.PUREGAMMA_BASE_URL}/systemone\`, {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.PUREGAMMA_API_KEY}\`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    model: "${selectedId}",
    state: "The build passed and every canary is green.",
    questions: ${systemOneQuestion},
  }),
});
const { answers } = await response.json();
console.log(answers.is_healthy.noul);`
      : `import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.PUREGAMMA_API_KEY,
  baseURL: process.env.PUREGAMMA_BASE_URL,
});

const response = await client.chat.completions.create({
  model: "${selectedId}",
  messages: [{ role: "user", content: "Hello from PureGamma." }],
});
console.log(response.choices[0].message.content);`,
    backend: `# .env.production / Vercel / Railway / Docker secret store
PUREGAMMA_API_KEY=sk-pg-...
PUREGAMMA_BASE_URL=${baseUrl}
PUREGAMMA_MODEL=${selectedId}

# Do not prefix these variables with NEXT_PUBLIC_.
# Do not ship sk-pg keys to the browser, desktop client, or mobile app.`,
    streamTools: `const stream = await client.chat.completions.create({
  model: "${selectedId}",
  stream: true,
  messages: [{ role: "user", content: "Summarize the report." }],
  tools: [{
    type: "function",
    function: {
      name: "lookup_price",
      description: "Read a price from your own service",
      parameters: {
        type: "object",
        properties: { symbol: { type: "string" } },
        required: ["symbol"],
      },
    },
  }],
});`,
  };

  const tabLabel = language === "curl" ? "cURL" : language === "python" ? "Python" : "Node.js";
  const activeSnippet = snippets[language];
  const status = pricingStatus(catalog, selectedCatalog, zh);

  const content = zh ? {
    eyebrow: "PureGamma API · OpenAI Compatible",
    title: "选择模型，复制配置，直接上线",
    description: "与 OpenAI SDK 兼容的轻量 API Gateway。使用您自己的 sk-pg 密钥和独立 API 预付余额；我们只路由到官方 Provider API。",
    console: "打开 API 控制台",
    fullDocs: "完整 API 文档",
    models: "模型目录",
    select: "选择模型后，Quick Start、代码示例与参数会同步切换。",
    perMillion: "按百万 tokens",
    modelId: "PureGamma 模型 ID",
    upstream: "官方上游 ID",
    context: "上下文",
    output: "最大输出",
    capabilities: "能力",
    overview: "模型概览",
    pricing: "定价",
    parameters: "请求参数",
    backend: "后端配置",
    source: "查看官方价格来源",
    currencyNote: "GLM 官方价格为中国区 CNY SKU。没有获批、可审计的汇率与地区策略前，不能将它作为 USD 钱包的可计费价格。",
    parameterDescription: "请求格式遵循 OpenAI Chat Completions；额外的 Provider 参数仅在模型能力允许时透传。",
    parameterRows: [
      ["model", "必填", "使用当前页面显示的 PureGamma 模型 ID。"],
      ["messages", "必填", "OpenAI messages 数组。"],
      ["stream", "可选", "true 时以 Server-Sent Events 返回。"],
      ["temperature", "0–2", "控制生成随机性；与 top_p 二选一进行调优。"],
      ["top_p", "0–1", "Nucleus sampling；通常不要和 temperature 同时调整。"],
      ["max_tokens", "1–131072", "输出上限；实际模型最大值以目录为准。"],
      ["response_format", "可选", "使用 JSON mode / JSON Schema 前先核对能力。"],
      ["tools / tool_choice", "可选", "函数调用输入不可信；执行前必须验证 schema 与权限。"],
    ],
    backendDescription: "把 Key 留在服务器的密钥管理或环境变量中。Vercel、Railway、Cloud Run、Docker 和自建后端都只需要这三项配置。",
    streamTitle: "流式与工具调用",
    streamDescription: "路由层支持 stream、JSON mode 和 tools。先从 GET /v1/models 核对启用能力；对外部 API、支付、数据库或文件执行工具调用前，请在您的服务端进行授权和参数验证。",
    walletTitle: "独立 API 余额",
    walletDescription: "中转站使用独立预付余额。Stripe 确认的金额 1:1 记入 API 钱包，不会消耗 PureGamma 产品订阅或 Credits。",
    quickStart: "Quick Start",
    quickDescription: "将所选模型接入任意 OpenAI 兼容客户端。",
    stepKey: "获取您的 API Key",
    stepKeyDescription: "在 API 控制台创建 sk-pg-… Key。明文只显示一次；请立即放入服务器密钥管理。",
    createKey: "创建 API Key",
    stepRequest: "发起第一个请求",
    stepRequestDescription: "使用当前所选模型 ID 和 OpenAI-compatible Base URL。",
    copy: "复制",
    copied: "已复制",
    activeModel: "当前模型",
    catalogNote: "实时模型可用性以带您的 API Key 的 GET /v1/models 返回为准。",
    safety: "不要把 sk-pg Key 写进 NEXT_PUBLIC_ 变量、前端 bundle、移动应用、仓库、截图或工单。疑似泄露时，请在 API 控制台暂停或轮换。",
    stack: "OpenAI SDK · Dify · LangChain · Cursor · Continue · Open WebUI",
  } : {
    eyebrow: "PureGamma API · OpenAI Compatible",
    title: "Choose a model, copy the configuration, and ship",
    description: "A lightweight OpenAI-compatible API Gateway. Use your own sk-pg key and separate prepaid API balance; PureGamma routes only to official provider APIs.",
    console: "Open API Console",
    fullDocs: "Full API docs",
    models: "Model catalog",
    select: "Select a model and the Quick Start, code samples, and parameters update together.",
    perMillion: "per 1M tokens",
    modelId: "PureGamma model ID",
    upstream: "Official upstream ID",
    context: "Context",
    output: "Max output",
    capabilities: "Capabilities",
    overview: "Model overview",
    pricing: "Pricing",
    parameters: "Request parameters",
    backend: "Backend configuration",
    source: "View official pricing source",
    currencyNote: "GLM's official SKU is a China-region CNY price. It cannot become a USD-wallet billable price until an auditable FX and regional policy is approved.",
    parameterDescription: "Requests follow OpenAI Chat Completions. Provider-specific fields are only forwarded when the selected model supports them.",
    parameterRows: [
      ["model", "Required", "Use the PureGamma model ID shown on this page."],
      ["messages", "Required", "A standard OpenAI messages array."],
      ["stream", "Optional", "When true, the response uses Server-Sent Events."],
      ["temperature", "0–2", "Controls randomness; tune it instead of top_p."],
      ["top_p", "0–1", "Nucleus sampling; normally do not tune it with temperature."],
      ["max_tokens", "1–131072", "Output ceiling; check the catalog for the actual model limit."],
      ["response_format", "Optional", "Check capability support before using JSON mode or JSON Schema."],
      ["tools / tool_choice", "Optional", "Tool arguments are untrusted; validate schema and permissions before execution."],
    ],
    backendDescription: "Keep the key in your server-side secret manager or environment. Vercel, Railway, Cloud Run, Docker, and your own backend only need these three values.",
    streamTitle: "Streaming and tool calls",
    streamDescription: "The router supports stream, JSON mode, and tools. Check enabled capability with GET /v1/models first; authorize and validate every tool argument on your server before it reaches an external API, payment, database, or file.",
    walletTitle: "Separate API balance",
    walletDescription: "The Gateway uses its own prepaid balance. A Stripe-confirmed payment credits the API wallet 1:1 and never consumes a PureGamma product subscription or Credits.",
    quickStart: "Quick Start",
    quickDescription: "Drop the selected model into any OpenAI-compatible client.",
    stepKey: "Get your API key",
    stepKeyDescription: "Create an sk-pg-… key in the API Console. Plaintext is shown once; move it into your server secret manager immediately.",
    createKey: "Create API Key",
    stepRequest: "Make your first request",
    stepRequestDescription: "Use the selected model ID with the OpenAI-compatible Base URL.",
    copy: "Copy",
    copied: "Copied",
    activeModel: "Selected model",
    catalogNote: "GET /v1/models with your API key is the source of truth for live model availability.",
    safety: "Never put an sk-pg key in a NEXT_PUBLIC_ variable, browser bundle, mobile app, repository, screenshot, or support ticket. Pause or rotate a suspected key in the API Console.",
    stack: "OpenAI SDK · Dify · LangChain · Cursor · Continue · Open WebUI",
  };

  return (
    /* `min-w-0 max-w-full` keeps the two wide tables and the long code lines
       inside their own scroll boxes. Each of those children already has
       `overflow-x-auto`, but `overflow` does not remove an element's min-content
       contribution to its ancestors, so without this the widest descendant (a
       720px table) still widened this block and pushed the page to 341px on a
       320px viewport. Measured before the fix: this element's scrollWidth was
       325 against a 288px clientWidth. */
    <div className="min-w-0 max-w-full pb-10">
      <PageHeader
        eyebrow={content.eyebrow}
        sectionNumber="API"
        title={content.title}
        description={content.description}
        actions={<>
          <Link href={withLocale(locale, "/gateway")} className="inline-flex min-h-10 items-center gap-2 border border-border-pg-strong bg-pg-white px-3 py-2 text-xs font-semibold text-pg-black rounded-lg"><KeyRound className="h-3.5 w-3.5" />{content.console}</Link>
          <a href={docsUrl} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-10 items-center gap-2 border border-border-pg px-3 py-2 text-xs text-text-pg-muted transition hover:border-border-pg-strong hover:text-text-pg rounded-lg"><ExternalLink className="h-3.5 w-3.5" />{content.fullDocs}</a>
        </>}
      />

      <section aria-label={content.models}>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div><div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim">01 / {content.models}</div><h2 className="mt-2 text-lg font-semibold text-text-pg">{content.models}</h2></div>
          <p className="max-w-xl text-sm leading-6 text-text-pg-muted">{content.select}</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
          {modelOrder.map((id) => {
            const model = catalogModels.find((candidate) => candidate.id === id);
            const info = narrativeFor(id, model, zh, modelCopy);
            const cardPricing = model?.pricing;
            const input = cardPricing?.official.input;
            const output = cardPricing?.official.output;
            const finalInput = cardPricing?.final.input;
            const finalOutput = cardPricing?.final.output;
            const isSelected = id === selectedId;
            const cardAvailability = model ? availabilityLabel(model, catalog, zh) : null;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setSelectedId(id)}
                aria-pressed={isSelected}
                className={`min-w-0 border p-4 text-left transition  rounded-xl ${isSelected ? "border-text-pg bg-bg-panel shadow-[inset_0_0_0_1px_var(--foreground)]" : "border-border-pg bg-bg-panel hover:border-border-pg-strong"}`}
              >
                <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{info.badge}</div><h3 className="mt-2 break-words text-sm font-semibold text-text-pg">{info.title}</h3></div><ChevronMark active={isSelected} /></div>
                <code className="mt-3 block break-all text-[11px] text-text-pg-muted">{id}</code>
                {cardAvailability ? <div className={`mt-2 inline-flex items-center gap-1 border px-1.5 py-0.5 text-[10px] rounded-lg ${model?.availability === "available" && catalog?.gateway_enabled ? "border-status-positive text-status-positive" : "border-border-pg text-text-pg-muted"}`}>{cardAvailability}</div> : null}
                <p className="mt-3 min-h-10 text-xs leading-5 text-text-pg-muted">{info.summary}</p>
                <div className="mt-4 border-t border-border-pg pt-3">
                  {input && output && finalInput && finalOutput ? <div className="mt-2 grid min-w-0 grid-cols-2 items-end gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:gap-2">
                    <div className="min-w-0">
                      <div className="break-words text-[9px] font-semibold uppercase leading-3 tracking-[0.1em] text-text-pg-dim">{officialPriceLabel}</div>
                      <div className="mt-1 font-mono text-xs text-text-pg">{priceAmount(input, cardPricing?.currency || "USD")} / {priceAmount(output, cardPricing?.currency || "USD")}</div>
                    </div>
                    <ArrowRight className="mb-0.5 hidden h-3.5 w-3.5 text-text-pg-dim sm:block" />
                    <div className="min-w-0 text-right">
                      <div className="break-words text-[9px] font-semibold uppercase leading-3 tracking-[0.1em] text-text-pg-dim">{finalPriceLabel}</div>
                      <div className="mt-1 font-mono text-xs font-semibold text-text-pg">{priceAmount(finalInput, cardPricing?.currency || "USD")} / {priceAmount(finalOutput, cardPricing?.currency || "USD")}</div>
                    </div>
                  </div> : <div className="mt-2 text-xs text-text-pg-dim">{zh ? "价格待审核" : "Price pending review"}</div>}
                  <div className="mt-1 text-[10px] text-text-pg-dim">{content.perMillion}</div>
                </div>
              </button>
            );
          })}
        </div>

        {/* The curated cards above are curated; this table is the catalog itself.
            A model this deployment starts serving is listed here even before
            anyone writes copy for it. */}
        <div className="mt-5 min-w-0 border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl" data-testid="catalog-model-table">
          <div className="flex min-w-0 flex-wrap items-end justify-between gap-3">
            <div>
              <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim">01b / {modelCopy.preview.catalogTitle}</div>
              <h2 className="mt-2 text-lg font-semibold text-text-pg">{modelCopy.preview.catalogTitle}</h2>
            </div>
            <p className="max-w-xl text-xs leading-5 text-text-pg-muted">{modelCopy.preview.catalogLead}</p>
          </div>
          {catalogModels.length ? (
            /* `min-w-0` on this wrapper is the actual fix, not the `overflow-x`
               below it. A flex/grid item defaults to `min-width: auto`, so it
               refuses to shrink below its content's intrinsic minimum — here the
               table's 720px. Without it the wrapper stayed 720px wide, the
               `overflow-x-auto` never had a narrower box to scroll inside, and
               the table pushed the whole page to 461px in a 393px viewport.
               `overflow-x-auto` alone was already present and did nothing. */
            <div className="mt-4 min-w-0 touch-pan-x overflow-x-auto overscroll-x-contain border border-border-pg rounded-xl">
              <table className="w-full min-w-[720px] text-left text-xs">
                <thead className="bg-bg-panel-muted text-[10px] uppercase tracking-[0.14em] text-text-pg-dim">
                  <tr>
                    <th className="px-3 py-3 font-medium">{modelCopy.preview.catalogName}</th>
                    <th className="px-3 py-3 font-medium">{modelCopy.preview.catalogId}</th>
                    <th className="px-3 py-3 font-medium">{modelCopy.preview.catalogProvider}</th>
                    <th className="px-3 py-3 font-medium">{modelCopy.preview.catalogUpstream}</th>
                    <th className="px-3 py-3 font-medium">{modelCopy.preview.catalogAvailability}</th>
                    <th className="px-3 py-3 font-medium">{modelCopy.preview.catalogPrice}</th>
                  </tr>
                </thead>
                <tbody>
                  {catalogModels.map((model) => {
                    const live = model.availability === "available" && Boolean(catalog?.gateway_enabled);
                    const input = model.pricing?.official.input;
                    const output = model.pricing?.official.output;
                    const symbol = model.pricing?.currency === "USD" ? "$" : model.pricing?.currency === "CNY" ? "¥" : `${model.pricing?.currency || ""} `;
                    return (
                      <tr key={model.id} className="border-t border-border-pg align-top">
                        <td className="px-3 py-3 font-medium text-text-pg">{model.display_name}</td>
                        <td className="px-3 py-3 font-mono text-text-pg-muted">
                          <button type="button" onClick={() => setSelectedId(model.id)} className="underline decoration-dotted underline-offset-2 hover:text-text-pg">{model.id}</button>
                        </td>
                        <td className="px-3 py-3 text-text-pg-muted">{providerLabel(model, model.id)}</td>
                        <td className="px-3 py-3 font-mono text-text-pg-muted">{model.provider_model_id}</td>
                        <td className="px-3 py-3"><span className={`inline-flex items-center gap-1 border px-1.5 py-0.5 rounded-lg ${live ? "border-status-positive text-status-positive" : "border-border-pg text-text-pg-muted"}`}>{availabilityLabel(model, catalog, zh)}</span></td>
                        <td className="px-3 py-3 font-mono text-text-pg-muted">{input && output ? `${symbol}${input.amount} / ${symbol}${output.amount}` : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-4 text-xs leading-5 text-text-pg-muted">{catalog?.unavailable ? modelCopy.preview.catalogUnavailable : modelCopy.preview.catalogEmpty}</p>
          )}
        </div>
      </section>

      {/* Both columns need an explicit `min-w-0`.
          The grid declares no column template below `xl`, so the implicit track
          sizes to content — and a table with `min-w-[720px]` inside made that
          track 445px inside a 361px container, which widened the entire page to
          461px on a 393px viewport. `min-width: auto` on the grid ITEMS is what
          let content inflate the track, so the constraint has to sit on the
          items; adding it further down the tree (the table wrapper) changed
          nothing, which is how the first attempt failed. */}
      <div className="mt-5 grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(390px,0.84fr)] xl:items-start">
        <main className="order-2 min-w-0 max-w-full space-y-5 xl:order-1">
          <section className="min-w-0 max-w-full border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl">
            <div className="flex flex-col items-start gap-4 sm:flex-row sm:justify-between">
              <div className="min-w-0 max-w-3xl"><div className="flex flex-wrap items-center gap-2"><span className="inline-flex items-center gap-1 border border-border-pg bg-bg-panel-muted px-2 py-1 text-[11px] text-text-pg-muted rounded-lg"><Layers3 className="h-3 w-3" />{selectedCatalog?.provider_display_name || (selectedId.startsWith("deepseek") ? "DeepSeek" : selectedId.startsWith("kimi") ? "Moonshot AI" : "Zhipu AI")}</span><span className="inline-flex max-w-full items-center gap-1 border border-border-pg px-2 py-1 text-[11px] text-text-pg-muted rounded-lg"><CircleDollarSign className="h-3 w-3 shrink-0" /><span className="break-words">{status}</span></span>{selectedAvailabilityLabel ? <span className={`inline-flex items-center gap-1 border px-2 py-1 text-[11px] rounded-lg ${availabilityIsLive ? "border-status-positive text-status-positive" : "border-border-pg text-text-pg-muted"}`}>{availabilityIsLive ? <Check className="h-3 w-3" /> : null}{selectedAvailabilityLabel}</span> : null}</div><h2 className="mt-4 text-xl font-semibold text-text-pg sm:text-2xl">{selectedName}</h2><p className="mt-3 text-sm leading-6 text-text-pg-muted">{narrative.detail}</p>{selectedCatalog?.metadata?.showcase_url ? <a href={selectedCatalog.metadata.showcase_url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex min-h-10 items-center gap-1.5 border border-border-pg px-2.5 py-2 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg"><ExternalLink className="h-3.5 w-3.5" />{zh ? selectedCatalog.metadata.showcase_label : selectedCatalog.metadata.showcase_label_en || selectedCatalog.metadata.showcase_label}</a> : null}</div>
              <div className="w-full border border-border-pg bg-bg-panel-muted p-3 text-left sm:w-auto sm:text-right rounded-lg"><div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{content.modelId}</div><code className="mt-2 block max-w-full break-all text-xs text-text-pg">{selectedId}</code><div className="mt-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{content.upstream}</div><code className="mt-2 block max-w-full break-all text-xs text-text-pg-muted">{selectedCatalog?.provider_model_id || "—"}</code></div>
            </div>
            <div className="mt-5 grid gap-px border border-border-pg bg-border-pg sm:grid-cols-3 rounded-xl overflow-hidden">
              <div className="bg-bg-panel p-4"><div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{content.context}</div><div className="mt-3 text-xl font-semibold text-text-pg">{compactTokens(selectedCatalog?.capabilities.max_context_tokens)}</div><div className="mt-1 text-xs text-text-pg-muted">{narrative.bestFor}</div></div>
              <div className="bg-bg-panel p-4"><div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{content.output}</div><div className="mt-3 text-xl font-semibold text-text-pg">{compactTokens(selectedCatalog?.capabilities.max_output_tokens)}</div><div className="mt-1 text-xs text-text-pg-muted">{zh ? "请求级 max_tokens 控制" : "Controlled by request max_tokens"}</div></div>
              <div className="bg-bg-panel p-4"><div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{content.capabilities}</div><div className="mt-3 flex flex-wrap gap-1.5">{[["stream", "Stream"], ["tool_calling", "Tools"], ["json_mode", "JSON"], ["reasoning", "Reasoning"]].map(([key, label]) => supports(selectedCatalog, key) ? <span key={key} className="border border-border-pg px-1.5 py-0.5 text-[10px] text-text-pg-muted rounded-lg">{label}</span> : null)}</div><div className="mt-3 text-xs text-text-pg-muted">{content.catalogNote}</div></div>
            </div>
          </section>

          <section className="min-w-0 max-w-full border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl">
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:justify-between sm:gap-4"><div><div className="flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim"><CircleDollarSign className="h-3.5 w-3.5" />02 / {content.pricing}</div><h2 className="mt-2 text-lg font-semibold text-text-pg">{pricingHeading}</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-text-pg-muted">{priceComparisonDescription}</p></div>{selectedCatalog?.source_reference ? <a href={selectedCatalog.source_reference} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-10 items-center gap-1.5 border border-border-pg px-2.5 py-2 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg rounded-lg"><ExternalLink className="h-3.5 w-3.5" />{content.source}</a> : null}</div>
            <div className="mt-5 grid gap-3 md:grid-cols-3"><PriceCompare label={zh ? "输入 / cache miss" : "Input / cache miss"} official={official.input} final={final.input} currency={currency} zh={zh} /><PriceCompare label={zh ? "输出" : "Output"} official={official.output} final={final.output} currency={currency} zh={zh} /><PriceCompare label={zh ? "缓存命中" : "Cache hit"} official={official.cache} final={final.cache} currency={currency} zh={zh} /></div>
            {selectedCatalog?.pricing?.status === "requires_currency_policy" ? <p className="mt-4 border-l-2 border-status-warning pl-3 text-xs leading-5 text-status-warning">{content.currencyNote}</p> : null}
          </section>

          <section className="min-w-0 max-w-full border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl">
            <div className="flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim"><SlidersHorizontal className="h-3.5 w-3.5" />03 / {content.parameters}</div><h2 className="mt-2 text-lg font-semibold text-text-pg">{content.parameters}</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-text-pg-muted">{content.parameterDescription}</p>
            <div className="mt-5 min-w-0 touch-pan-x overflow-x-auto overscroll-x-contain border border-border-pg rounded-xl"><table className="w-full min-w-[640px] text-left text-xs"><thead className="bg-bg-panel-muted text-[10px] uppercase tracking-[0.14em] text-text-pg-dim"><tr><th className="px-3 py-3 font-medium">Parameter</th><th className="px-3 py-3 font-medium">Type / range</th><th className="px-3 py-3 font-medium">{zh ? "说明" : "Description"}</th></tr></thead><tbody>{content.parameterRows.map(([name, range, description]) => <tr key={name} className="border-t border-border-pg align-top"><td className="px-3 py-3 font-mono text-text-pg">{name}</td><td className="px-3 py-3 text-text-pg-muted">{range}</td><td className="px-3 py-3 leading-5 text-text-pg-muted">{description}</td></tr>)}</tbody></table></div>
          </section>

          <section className="min-w-0 max-w-full border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl">
            <div className="flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim"><ServerCog className="h-3.5 w-3.5" />04 / {content.backend}</div><h2 className="mt-2 text-lg font-semibold text-text-pg">{content.backend}</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-text-pg-muted">{content.backendDescription}</p><div className="mt-5 min-w-0 max-w-full"><CodeBlock language=".env.production" value={snippets.backend} copyLabel={content.copy} copiedLabel={content.copied} /></div>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <section className="min-w-0 max-w-full border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl"><div className="flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim"><Zap className="h-3.5 w-3.5" />{content.streamTitle}</div><p className="mt-3 text-sm leading-6 text-text-pg-muted">{content.streamDescription}</p><div className="mt-4"><CodeBlock language="TypeScript" value={snippets.streamTools} copyLabel={content.copy} copiedLabel={content.copied} compact /></div></section>
            <section className="min-w-0 max-w-full border border-border-pg bg-bg-panel p-4 sm:p-5 rounded-xl"><div className="flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim"><WalletCards className="h-3.5 w-3.5" />{content.walletTitle}</div><p className="mt-3 text-sm leading-6 text-text-pg-muted">{content.walletDescription}</p><div className="mt-5 border-t border-border-pg pt-4 text-xs leading-5 text-text-pg-muted"><LockKeyhole className="mr-1.5 inline h-3.5 w-3.5 align-text-bottom" />{content.safety}</div></section>
          </div>
        </main>

        <aside className="order-1 min-w-0 max-w-full border border-border-pg bg-bg-panel xl:sticky xl:top-6 xl:order-2 rounded-lg">
          <div className="border-b border-border-pg px-4 py-4 sm:px-5"><div className="flex flex-wrap items-start justify-between gap-2"><div className="inline-flex items-center gap-2 text-lg font-semibold text-text-pg"><Sparkles className="h-4 w-4" />{content.quickStart}</div><span className="max-w-full overflow-x-auto whitespace-nowrap border border-border-pg px-2 py-1 font-mono text-[10px] text-text-pg-muted rounded-lg">{selectedId}</span></div><p className="mt-2 text-sm leading-6 text-text-pg-muted">{content.quickDescription}</p></div>
          <div className="space-y-5 p-4 sm:p-5">
            <div><div className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-bg-panel-muted text-xs font-semibold text-text-pg">1</span><div className="min-w-0"><h2 className="font-semibold text-text-pg">{content.stepKey}</h2><p className="mt-1 text-sm leading-6 text-text-pg-muted">{content.stepKeyDescription}</p><Link href={withLocale(locale, "/gateway")} className="mt-3 inline-flex min-h-10 items-center gap-2 border border-border-pg-strong bg-pg-white px-3 py-2 text-xs font-semibold text-pg-black rounded-lg"><KeyRound className="h-3.5 w-3.5" />{content.createKey}</Link></div></div><div className="mt-4"><CodeBlock language=".env" value={snippets.env} copyLabel={content.copy} copiedLabel={content.copied} compact /></div></div>
            <div className="border-t border-border-pg pt-5"><div className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-bg-panel-muted text-xs font-semibold text-text-pg">2</span><div className="min-w-0"><h2 className="font-semibold text-text-pg">{content.stepRequest}</h2><p className="mt-1 text-sm leading-6 text-text-pg-muted">{content.stepRequestDescription}</p></div></div><div className="mt-4 min-w-0 flex flex-wrap gap-1 border-b border-border-pg"><CodeTab active={language === "curl"} onClick={() => setLanguage("curl")} label="cURL" /><CodeTab active={language === "python"} onClick={() => setLanguage("python")} label="Python" /><CodeTab active={language === "node"} onClick={() => setLanguage("node")} label="Node.js" /></div><div className="mt-3"><CodeBlock language={tabLabel} value={activeSnippet} copyLabel={content.copy} copiedLabel={content.copied} compact /></div></div>
            <div className="border-t border-border-pg pt-5"><div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{content.activeModel}</div><div className="mt-2 flex items-center justify-between gap-3"><div className="min-w-0"><div className="text-sm font-semibold text-text-pg">{selectedName}</div><code className="break-all text-xs text-text-pg-muted">{selectedId}</code></div><Code2 className="h-5 w-5 shrink-0 text-text-pg-dim" /></div><p className="mt-3 text-xs leading-5 text-text-pg-muted">{content.stack}</p></div>
          </div>
          <div className="border-t border-border-pg px-4 py-4 text-xs leading-5 text-text-pg-muted sm:px-5"><Terminal className="mr-1.5 inline h-3.5 w-3.5 align-text-bottom" />{content.catalogNote}</div>
        </aside>
      </div>
    </div>
  );
}

function ChevronMark({ active }: { active: boolean }) {
  return <span className={`flex h-6 w-6 shrink-0 items-center justify-center border  rounded-lg ${active ? "border-text-pg bg-pg-white text-pg-black" : "border-border-pg text-text-pg-dim"}`}><ArrowRight className="h-3.5 w-3.5" /></span>;
}

function CodeTab({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return <button type="button" onClick={onClick} className={`min-h-10 border-b-2 px-3 py-2 text-xs transition ${active ? "border-text-pg text-text-pg" : "border-transparent text-text-pg-muted hover:text-text-pg"}`}>{label}</button>;
}
