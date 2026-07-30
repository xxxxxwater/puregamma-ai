"use client";

import { ExternalLink, Network } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";

const docsBaseUrl = (process.env.NEXT_PUBLIC_DOCS_URL || "https://puregamma-ai.gitbook.io/puregamma-ai").replace(/\/+$/, "");
const chineseApiDocsUrl = (process.env.NEXT_PUBLIC_API_DOCS_ZH_URL || `${docsBaseUrl}/api-gateway`).replace(/\/+$/, "");
const englishApiDocsUrl = (process.env.NEXT_PUBLIC_API_DOCS_EN_URL || `${docsBaseUrl}/api-gateway-en`).replace(/\/+$/, "");

/** A locale-aware, in-product entry point for the published API GitBook. */
export function ApiDocsEmbed() {
  const locale = useLocale();
  const zh = locale === "zh";
  const docsUrl = zh ? chineseApiDocsUrl : englishApiDocsUrl;

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3 border border-border-pg bg-bg-panel px-4 py-3">
        <div className="flex items-center gap-2">
          <Network className="h-4 w-4 text-text-pg-muted" />
          <div>
            <h1 className="text-sm font-semibold text-text-pg">{zh ? "PureGamma API" : "PureGamma API"}</h1>
            <p className="text-xs text-text-pg-muted">
              {zh ? "OpenAI 兼容接口、Key 管理、用量与计费说明" : "OpenAI-compatible API, key management, usage, and billing"}
            </p>
          </div>
        </div>
        <a
          href={docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted transition-colors hover:text-text-pg"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          {zh ? "在 GitBook 中打开" : "Open in GitBook"}
        </a>
      </div>
      <iframe
        src={docsUrl}
        title={zh ? "PureGamma API 文档" : "PureGamma API documentation"}
        className="min-h-0 w-full flex-1 border border-border-pg bg-white"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}
