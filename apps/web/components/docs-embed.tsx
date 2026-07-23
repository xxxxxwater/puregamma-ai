"use client";

import { ExternalLink, LifeBuoy } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";

const DOCS_BASE_URL = (process.env.NEXT_PUBLIC_DOCS_URL || "https://puregamma-ai.gitbook.io/puregamma-ai").replace(/\/+$/, "");

/**
 * In-app preview of the product documentation hosted on GitBook.
 * Deep-links the English subtree for en locale, the Chinese tree (root) for zh.
 */
export function DocsEmbed() {
  const locale = useLocale();
  const zh = locale === "zh";
  const docsUrl = zh ? `${DOCS_BASE_URL}/` : `${DOCS_BASE_URL}/english/getting-started`;

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-3">
      <div className="flex items-center justify-between border border-border-pg bg-bg-panel px-4 py-3">
        <div className="flex items-center gap-2">
          <LifeBuoy className="h-4 w-4 text-text-pg-muted" />
          <h1 className="text-sm font-semibold text-text-pg">{zh ? "帮助文档" : "Documentation"}</h1>
          <span className="text-xs text-text-pg-muted">{zh ? "使用手册 · 功能指南 · 常见问题" : "User guide · Features · FAQ"}</span>
        </div>
        <a
          href={docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted transition-colors hover:text-text-pg"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          {zh ? "新窗口打开" : "Open in new tab"}
        </a>
      </div>
      <iframe
        src={docsUrl}
        title={zh ? "PureGamma AI 帮助文档" : "PureGamma AI documentation"}
        className="min-h-0 w-full flex-1 border border-border-pg bg-white"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}
