"use client";

import Link from "next/link";
import { Check, Copy, ExternalLink, KeyRound, Terminal, WalletCards } from "lucide-react";
import { useState } from "react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { PageHeader, ResearchCard } from "@/components/puregamma";
import { withLocale } from "@/i18n/routing";

const baseUrl = "https://api.puregamma.ai/v1";
const docsBaseUrl = (process.env.NEXT_PUBLIC_DOCS_URL || "https://puregamma-ai.gitbook.io/puregamma-ai").replace(/\/+$/, "");

const snippets = {
  env: `PUREGAMMA_API_KEY=sk-pg-...
PUREGAMMA_BASE_URL=${baseUrl}
# Use an exact id returned by GET /v1/models
PUREGAMMA_MODEL=deepseek-v4-flash`,
  curl: `curl -sS ${baseUrl}/chat/completions \\
  -H "Authorization: Bearer $PUREGAMMA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "Hello from PureGamma."}]
  }'`,
  python: `from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["PUREGAMMA_API_KEY"],
    base_url="${baseUrl}",
)

response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "Hello from PureGamma."}],
)
print(response.choices[0].message.content)`,
  node: `import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.PUREGAMMA_API_KEY,
  baseURL: "${baseUrl}",
});

const response = await client.chat.completions.create({
  model: "deepseek-v4-flash",
  messages: [{ role: "user", content: "Hello from PureGamma." }],
});
console.log(response.choices[0].message.content);`,
};

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
      className="inline-flex items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted transition hover:border-border-pg-strong hover:text-text-pg"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-status-positive" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? copiedLabel : label}
    </button>
  );
}

function CodeBlock({ language, value, copyLabel, copiedLabel }: { language: string; value: string; copyLabel: string; copiedLabel: string }) {
  return (
    <div className="overflow-hidden border border-border-pg bg-bg-app">
      <div className="flex items-center justify-between border-b border-border-pg px-3 py-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-pg-dim">{language}</span>
        <CopyButton value={value} label={copyLabel} copiedLabel={copiedLabel} />
      </div>
      <pre className="overflow-x-auto p-4 text-xs leading-6 text-text-pg"><code>{value}</code></pre>
    </div>
  );
}

/** A public, in-product quickstart; the longer GitBook guide remains linked below. */
export function ApiDocsEmbed() {
  const locale = useLocale();
  const zh = locale === "zh";
  const docsUrl = zh ? `${docsBaseUrl}/api-gateway` : `${docsBaseUrl}/api-gateway-en`;
  const copy = zh ? {
    eyebrow: "PureGamma API · OpenAI Compatible",
    title: "三步接入 PureGamma API",
    description: "将 Base URL 和您自己的 sk-pg Key 填入任何 OpenAI 兼容客户端，即可调用已启用模型。无需部署或管理上游 Provider。",
    console: "打开 API 控制台",
    fullDocs: "完整 API 文档",
    stepTitle: "开始前",
    steps: [
      ["创建 Key", "在 API 控制台创建 sk-pg-... Key；明文仅显示一次。"],
      ["充值 API 余额", "Gateway 使用独立的预付 USD 余额，不使用订阅 Credits。"],
      ["复制配置", "将下方 Base URL、Key 和模型 ID 填入服务端或兼容客户端。"],
    ],
    configTitle: "中转站配置卡",
    configDesc: "适用于 OpenAI SDK、Dify、LangChain、Cursor、Continue、Open WebUI 和自建后端。",
    fields: [
      ["API 类型", "OpenAI Compatible / OpenAI API"],
      ["Base URL", baseUrl],
      ["API Key", "sk-pg-...（只放在环境变量或密钥管理服务）"],
      ["模型", "从 GET /v1/models 返回的精确 id 中选择"],
    ],
    modelsTitle: "模型怎么选",
    modelsDesc: "下列是公共兼容 ID。实际可用性以您的 GET /v1/models 返回为准。",
    modelRows: [
      ["deepseek-v4-flash", "默认", "低延迟对话、批量任务和性价比优先场景"],
      ["deepseek-v4-pro", "复杂任务", "更复杂的推理、代码与长回答"],
      ["kimi-k3-max", "长上下文", "长文档、复杂工具工作流"],
      ["glm-5.2", "通用", "中英文通用任务与工具调用"],
    ],
    modelNote: "模型、JSON、流式和工具调用能力会随 Provider 健康与价格审核状态变化；先请求 /v1/models，再用返回的 id 发起调用。",
    deployTitle: "最小可用部署",
    deployDesc: "Key 始终只存在于服务端。把环境变量配置到 Vercel、Railway、Docker、Cloud Run 或您自己的后端即可。",
    envLabel: "复制 .env",
    curlTitle: "先跑一个请求",
    curlDesc: "无需安装 SDK；把环境变量换成您的 Key 后直接执行。",
    curlLabel: "复制 curl",
    sdkTitle: "使用官方 OpenAI SDK",
    pythonLabel: "复制 Python",
    nodeLabel: "复制 Node.js",
    streamTitle: "流式与工具调用",
    stream: "Chat Completions 兼容 stream: true、JSON mode 和 tools。是否启用以模型列表中的 capabilities 为准；工具参数是未验证输入，调用数据库、支付、网络或文件前必须自行校验权限与 schema。",
    safetyTitle: "安全与计费",
    safety: "不要把 sk-pg Key 写进浏览器代码、移动 App、仓库、截图或工单。怀疑泄露时在 API 控制台暂停或轮换。每次调用只从 Gateway 预付 USD 余额扣费；余额不足返回 402。",
    more: "需要流式、工具调用、错误码或管理员 Provider 配置？",
    moreLink: "打开完整文档",
    copied: "已复制",
  } : {
    eyebrow: "PureGamma API · OpenAI Compatible",
    title: "Connect to the PureGamma API in three steps",
    description: "Use your sk-pg key and this Base URL in any OpenAI-compatible client. PureGamma handles routing only to enabled providers; you do not manage upstream provider connections.",
    console: "Open API Console",
    fullDocs: "Full API docs",
    stepTitle: "Before you start",
    steps: [
      ["Create a key", "Create an sk-pg-... key in the API Console. The plaintext key is shown once."],
      ["Add API balance", "Gateway uses its own prepaid USD balance, separate from product Credits."],
      ["Copy configuration", "Put the Base URL, key, and a returned model ID into your server or compatible client."],
    ],
    configTitle: "Gateway configuration card",
    configDesc: "Works with the OpenAI SDK, Dify, LangChain, Cursor, Continue, Open WebUI, and your own backend.",
    fields: [
      ["API type", "OpenAI Compatible / OpenAI API"],
      ["Base URL", baseUrl],
      ["API key", "sk-pg-... (environment variable or secret manager only)"],
      ["Model", "An exact id returned by GET /v1/models"],
    ],
    modelsTitle: "Choose a model",
    modelsDesc: "These are public compatibility IDs. Your GET /v1/models response is the source of truth for availability.",
    modelRows: [
      ["deepseek-v4-flash", "Default", "Low-latency chat, batch work, and value-oriented tasks"],
      ["deepseek-v4-pro", "Complex", "More demanding reasoning, code, and longer answers"],
      ["kimi-k3-max", "Long context", "Long documents and complex tool workflows"],
      ["glm-5.2", "General", "General Chinese/English tasks and tool calls"],
    ],
    modelNote: "Model availability and JSON, streaming, or tool support may change with provider health and price approval. Request /v1/models first, then use an id it returns.",
    deployTitle: "Minimal deployment",
    deployDesc: "Keep the key server-side. Add these variables in Vercel, Railway, Docker, Cloud Run, or your own backend.",
    envLabel: "Copy .env",
    curlTitle: "Run one request first",
    curlDesc: "No SDK needed. Replace the environment variable with your own key and run this command.",
    curlLabel: "Copy curl",
    sdkTitle: "Use the official OpenAI SDK",
    pythonLabel: "Copy Python",
    nodeLabel: "Copy Node.js",
    streamTitle: "Streaming and tools",
    stream: "Chat Completions supports stream: true, JSON mode, and tools. Check the selected model's capabilities before enabling them. Tool arguments are untrusted input: validate schema and permissions before they touch databases, payments, networks, or files.",
    safetyTitle: "Security and billing",
    safety: "Never place an sk-pg key in browser code, a mobile app, a repository, a screenshot, or a support ticket. Pause or rotate a suspected key in the API Console. Each request debits Gateway prepaid USD balance only; insufficient balance returns 402.",
    more: "Need streaming, tool calls, error codes, or provider configuration for administrators?",
    moreLink: "Open full documentation",
    copied: "Copied",
  };

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow={copy.eyebrow}
        sectionNumber="API"
        title={copy.title}
        description={copy.description}
        actions={<>
          <Link href={withLocale(locale, "/gateway")} className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-3 py-2 text-xs font-semibold text-pg-black"><KeyRound className="h-3.5 w-3.5" />{copy.console}</Link>
          <a href={docsUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 border border-border-pg px-3 py-2 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"><ExternalLink className="h-3.5 w-3.5" />{copy.fullDocs}</a>
        </>}
      />

      <section>
        <h2 className="mb-3 text-sm font-semibold">{copy.stepTitle}</h2>
        <div className="grid gap-px border border-border-pg bg-border-pg md:grid-cols-3">
          {copy.steps.map(([title, detail], index) => <div key={title} className="bg-bg-panel p-4"><div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-dim">{String(index + 1).padStart(2, "0")}</div><h3 className="mt-4 text-sm font-semibold">{title}</h3><p className="mt-2 text-xs leading-5 text-text-pg-muted">{detail}</p></div>)}
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <ResearchCard>
          <h2 className="text-base font-semibold">{copy.configTitle}</h2>
          <p className="mt-2 text-sm leading-6 text-text-pg-muted">{copy.configDesc}</p>
          <dl className="mt-5 divide-y divide-border-pg border-y border-border-pg text-sm">
            {copy.fields.map(([label, value]) => <div key={label} className="grid gap-1 py-3 sm:grid-cols-[130px_1fr]"><dt className="text-text-pg-muted">{label}</dt><dd className={value === baseUrl ? "font-mono text-xs text-text-pg" : "text-text-pg"}>{value}</dd></div>)}
          </dl>
          <div className="mt-5"><CodeBlock language=".env" value={snippets.env} copyLabel={copy.envLabel} copiedLabel={copy.copied} /></div>
        </ResearchCard>

        <ResearchCard>
          <h2 className="text-base font-semibold">{copy.modelsTitle}</h2>
          <p className="mt-2 text-sm leading-6 text-text-pg-muted">{copy.modelsDesc}</p>
          <div className="mt-5 divide-y divide-border-pg border-y border-border-pg">
            {copy.modelRows.map(([id, use, detail]) => <div key={id} className="grid gap-1 py-3 sm:grid-cols-[160px_90px_1fr]"><code className="text-xs text-text-pg">{id}</code><span className="text-xs font-medium text-text-pg">{use}</span><span className="text-xs leading-5 text-text-pg-muted">{detail}</span></div>)}
          </div>
          <p className="mt-4 text-xs leading-5 text-text-pg-dim">{copy.modelNote}</p>
        </ResearchCard>
      </div>

      <section className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <ResearchCard>
          <div className="flex items-start gap-3"><Terminal className="mt-0.5 h-5 w-5 shrink-0" /><div><h2 className="text-base font-semibold">{copy.curlTitle}</h2><p className="mt-2 text-sm leading-6 text-text-pg-muted">{copy.curlDesc}</p></div></div>
          <div className="mt-5"><CodeBlock language="curl" value={snippets.curl} copyLabel={copy.curlLabel} copiedLabel={copy.copied} /></div>
        </ResearchCard>
        <ResearchCard>
          <h2 className="text-base font-semibold">{copy.sdkTitle}</h2>
          <p className="mt-2 text-sm leading-6 text-text-pg-muted">{copy.deployTitle} · {copy.deployDesc}</p>
          <div className="mt-5 grid gap-4 2xl:grid-cols-2"><CodeBlock language="Python" value={snippets.python} copyLabel={copy.pythonLabel} copiedLabel={copy.copied} /><CodeBlock language="Node.js" value={snippets.node} copyLabel={copy.nodeLabel} copiedLabel={copy.copied} /></div>
        </ResearchCard>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <ResearchCard><h2 className="text-base font-semibold">{copy.streamTitle}</h2><p className="mt-3 text-sm leading-6 text-text-pg-muted">{copy.stream}</p></ResearchCard>
        <ResearchCard><div className="flex items-start gap-3"><WalletCards className="mt-0.5 h-5 w-5 shrink-0" /><div><h2 className="text-base font-semibold">{copy.safetyTitle}</h2><p className="mt-3 text-sm leading-6 text-text-pg-muted">{copy.safety}</p></div></div></ResearchCard>
      </div>

      <p className="border-t border-border-pg pt-5 text-sm text-text-pg-muted">{copy.more} <a href={docsUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-text-pg underline underline-offset-4">{copy.moreLink}<ExternalLink className="h-3.5 w-3.5" /></a></p>
    </div>
  );
}
