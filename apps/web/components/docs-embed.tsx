"use client";

import { useState } from "react";
import { ExternalLink, LifeBuoy } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";

const DOCS_BASE_URL = (process.env.NEXT_PUBLIC_DOCS_URL || "https://puregamma-ai.gitbook.io/puregamma-ai").replace(/\/+$/, "");

type DocSection = { key: string; label: string; path: string };

const SECTIONS: Record<"en" | "zh", DocSection[]> = {
  en: [
    { key: "getting-started", label: "Getting Started", path: "/english/getting-started" },
    { key: "features", label: "Feature Guide", path: "/english/feature-guide" },
    { key: "billing", label: "Billing & Credits", path: "/english/billing-and-credits" },
    { key: "faq", label: "FAQ & Roadmap", path: "/english/faq-and-roadmap" },
  ],
  zh: [
    { key: "getting-started", label: "快速上手", path: "/kuai-su-shang-shou" },
    { key: "features", label: "功能指南", path: "/gong-neng-zhi-nan" },
    { key: "billing", label: "订阅与 Credits", path: "/ding-yue-yu-credits" },
    { key: "account", label: "账户与安全", path: "/zhang-hu-yu-an-quan" },
    { key: "faq", label: "常见问题", path: "/chang-jian-wen-ti" },
    { key: "api", label: "API Gateway", path: "/api-gateway" },
  ],
};

/**
 * In-app preview of the product documentation hosted on GitBook with an
 * in-app section navigator, so readers never leave the product to browse.
 */
export function DocsEmbed() {
  const locale = useLocale();
  const zh = locale === "zh";
  const sections = SECTIONS[locale];
  const [activeKey, setActiveKey] = useState(sections[0]?.key ?? "getting-started");
  const active = sections.find((section) => section.key === activeKey) ?? sections[0];
  const docsUrl = active ? `${DOCS_BASE_URL}${active.path}` : DOCS_BASE_URL;

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-3">
      <div className="flex items-center justify-between gap-3 border border-border-pg bg-bg-panel px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <LifeBuoy className="h-4 w-4 shrink-0 text-text-pg-muted" />
          <h1 className="text-sm font-semibold text-text-pg">{zh ? "帮助文档" : "Documentation"}</h1>
          <span className="hidden text-xs text-text-pg-muted sm:block">{zh ? "使用手册 · 功能指南 · 常见问题" : "User guide · Features · FAQ"}</span>
        </div>
        <a
          href={docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex shrink-0 items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted transition-colors hover:text-text-pg"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          {zh ? "新窗口打开" : "Open in new tab"}
        </a>
      </div>
      <nav className="flex flex-wrap gap-1.5" aria-label={zh ? "文档章节" : "Documentation sections"}>
        {sections.map((section) => (
          <button
            key={section.key}
            type="button"
            onClick={() => setActiveKey(section.key)}
            aria-current={section.key === active?.key ? "page" : undefined}
            className={`border px-2.5 py-1.5 text-xs ${section.key === active?.key ? "border-border-pg-strong bg-bg-panel-muted font-semibold text-text-pg" : "border-border-pg text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"}`}
          >
            {section.label}
          </button>
        ))}
      </nav>
      <iframe
        key={docsUrl}
        src={docsUrl}
        title={zh ? "PureGamma AI 帮助文档" : "PureGamma AI documentation"}
        className="min-h-0 w-full flex-1 border border-border-pg bg-white"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}
