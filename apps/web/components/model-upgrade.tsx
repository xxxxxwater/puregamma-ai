"use client";

import Link from "next/link";
import { ArrowRight, Check, CircleAlert, CircleDashed, Copy, MinusCircle } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/puregamma";
import type { GatewayCatalog } from "@/lib/api";
import { FLASH_ALIAS_ID, FLASH_MODEL_ID, compactTokens, flashAvailability, type ModelCatalogState } from "@/lib/model-catalog";
import { withLocale, type Locale } from "@/i18n/routing";
import { getMessageNamespace } from "@/lib/translations";

function availabilityCopy(state: ModelCatalogState, copy: ModelCopy) {
  if (state === "available") {
    return {
      label: copy.stateLive,
      detail: copy.preview.availabilityDetailLive,
      tone: "emerald" as const,
      icon: <Check className="h-3 w-3" aria-hidden />,
    };
  }
  if (state === "pending") {
    return {
      label: copy.statePending,
      detail: copy.preview.availabilityDetailPending,
      tone: "amber" as const,
      icon: <CircleDashed className="h-3 w-3" aria-hidden />,
    };
  }
  if (state === "unavailable") {
    return {
      label: copy.stateUnavailable,
      detail: copy.preview.availabilityDetailPending,
      tone: "neutral" as const,
      icon: <MinusCircle className="h-3 w-3" aria-hidden />,
    };
  }
  return {
    label: copy.stateUnverified,
    detail: copy.preview.availabilityDetailUnverified,
    tone: "neutral" as const,
    icon: <CircleAlert className="h-3 w-3" aria-hidden />,
  };
}

type ModelCopy = ReturnType<typeof getMessageNamespace<"model-upgrade">>;

function FactRow({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-sm leading-6 text-text-pg-muted">
      <Check className="mt-1 h-3.5 w-3.5 shrink-0 text-status-positive" aria-hidden />
      <span className="min-w-0">{children}</span>
    </li>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 border-t border-border-pg pt-2 first:border-t-0 first:pt-0 sm:flex-row sm:items-baseline sm:justify-between sm:gap-3">
      <dt className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{label}</dt>
      {/* Muted, not `text-text-pg`: the primary token is tuned for headings and
          loses contrast against the muted panel in the light theme. */}
      <dd className="min-w-0 break-all font-mono text-xs text-text-pg-muted">{value}</dd>
    </div>
  );
}

/**
 * Homepage product preview for the DeepSeek V4.1 Flash upgrade.
 *
 * Every value shown (availability, ids, context window, price) comes from the
 * catalog the deployment really serves. Model copy that cannot be verified is
 * replaced by an explicit empty state instead of an invented number.
 */
export function ModelUpgradePreview({ locale, catalog }: { locale: Locale; catalog: GatewayCatalog | null }) {
  const copy = getMessageNamespace(locale, "model-upgrade");
  const { state, model } = flashAvailability(catalog);
  const availability = availabilityCopy(state, copy);
  const alias = catalog?.models.find((item) => item.id === FLASH_ALIAS_ID) ?? null;

  const contextWindow = compactTokens(model?.capabilities.max_context_tokens);
  const input = model?.pricing?.official.input;
  const output = model?.pricing?.official.output;
  const currency = model?.pricing?.currency ?? "USD";
  const symbol = currency === "USD" ? "$" : currency === "CNY" ? "¥" : `${currency} `;
  const priceReviewed = model?.pricing?.status === "active" && Boolean(input && output);

  const sampleRequest = `curl -sS https://api.puregamma.ai/v1/chat/completions \\
  -H "Authorization: Bearer $PUREGAMMA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${FLASH_MODEL_ID}",
    "messages": [{"role": "user", "content": "Hello from PureGamma."}]
  }'`;

  const [copied, setCopied] = useState("");
  const copyValue = async (key: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied((current) => (current === key ? "" : current)), 1600);
    } catch {
      setCopied("");
    }
  };

  return (
    <section
      aria-labelledby="model-upgrade-title"
      className="border border-border-pg bg-bg-panel p-6 md:p-8 rounded-2xl"
      data-testid="model-upgrade-preview"
      data-model-availability={state}
    >
      <div className="flex flex-wrap items-center gap-3">
        <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-dim">{copy.preview.eyebrow}</div>
        <Badge tone={availability.tone}>
          <span className="inline-flex items-center gap-1.5">{availability.icon}{availability.label}</span>
        </Badge>
      </div>

      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id="model-upgrade-title" className="text-xl font-semibold text-text-pg md:text-2xl">
            {copy.modelName}
          </h2>
          <p className="mt-2 max-w-3xl text-base font-medium text-text-pg">{copy.announcement}</p>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-text-pg-muted">{copy.preview.lead}</p>
        </div>
        <Link
          href={withLocale(locale, "/api")}
          className="inline-flex min-h-10 shrink-0 items-center gap-2 border border-border-pg px-3 py-2 text-xs font-semibold text-text-pg transition hover:border-border-pg-strong rounded-lg"
        >
          {copy.preview.docsCta} <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      </div>

      {/* Secondary, small-print block: what the catalog state does and does not
          mean. Keeps the "published + priced" claim separate from runtime
          health, which this page cannot see. */}
      <div className="mt-5 border border-border-pg bg-bg-panel-muted p-3 rounded-xl">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{copy.preview.availability}</span>
          <Badge tone={availability.tone}>
            <span className="inline-flex items-center gap-1.5">{availability.icon}{availability.label}</span>
          </Badge>
        </div>
        <p className="mt-2 text-xs leading-5 text-text-pg-muted">{availability.detail}</p>
        <p className="mt-1 text-[11px] leading-5 text-text-pg-dim">{copy.preview.runtimeNote}</p>
      </div>

      <h3 className="mt-7 text-sm font-semibold text-text-pg">{copy.preview.whereTitle}</h3>
      <div className="mt-3 grid gap-3 lg:grid-cols-[1.35fr_1fr]">
        <div className="flex min-w-0 flex-col border border-border-pg bg-bg-panel p-4 rounded-xl">
          <h4 className="text-sm font-semibold text-text-pg">{copy.preview.chatTitle}</h4>
          <p className="mt-2 flex-1 text-xs leading-5 text-text-pg-muted">{copy.preview.chatBody}</p>
          <p className="mt-2 text-[10px] uppercase tracking-[0.1em] text-text-pg-dim">{copy.preview.chatDetail}</p>
          <Link
            href={withLocale(locale, "/chat")}
            className="mt-3 inline-flex min-h-10 items-center justify-center gap-2 border border-border-pg-strong bg-pg-white px-3 py-2 text-xs font-semibold text-pg-black rounded-lg"
          >
            {copy.preview.chatCta} <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </div>
        <div className="flex min-w-0 flex-col border border-border-pg bg-bg-panel p-4 rounded-xl">
          <h4 className="text-sm font-semibold text-text-pg">{copy.preview.gatewayTitle}</h4>
          <p className="mt-2 flex-1 text-xs leading-5 text-text-pg-muted">{copy.preview.gatewayBody}</p>
          <p className="mt-2 text-[10px] uppercase tracking-[0.1em] text-text-pg-dim">{copy.preview.gatewayDetail}</p>
          <Link
            href={withLocale(locale, "/gateway")}
            className="mt-3 inline-flex min-h-10 items-center justify-center gap-2 border border-border-pg-strong bg-pg-white px-3 py-2 text-xs font-semibold text-pg-black rounded-lg"
          >
            {copy.preview.gatewayCta} <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-text-pg">{copy.preview.routesTitle}</h3>
          <ul className="mt-3 space-y-1.5">
            {copy.preview.routes.map((route) => <FactRow key={route}>{route}</FactRow>)}
          </ul>
          <p className="mt-3 text-xs leading-5 text-text-pg-dim">{copy.preview.routesNote}</p>
        </div>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-text-pg">{copy.preview.factsTitle}</h3>
          <ul className="mt-3 space-y-1.5">
            <FactRow>{copy.preview.factStreaming}</FactRow>
            <FactRow>{copy.preview.factTools}</FactRow>
            <FactRow>{copy.preview.factThinking}</FactRow>
          </ul>
          <p className="mt-3 text-xs leading-5 text-text-pg-dim">{copy.preview.factUnverified}</p>
          <p className="mt-3 text-[10px] uppercase tracking-[0.1em] text-text-pg-dim">{copy.preview.clientsTitle}</p>
          <p className="mt-1 text-xs leading-5 text-text-pg-muted">{copy.preview.clients}</p>
        </div>
      </div>

      {/* Technical fields (ids, catalog limits, pricing, raw request example) are
          secondary for a product page: collapsed by default, and the API
          reference and Gateway console remain the authoritative surfaces. */}
      <details className="mt-6 border border-border-pg bg-bg-panel-muted rounded-xl" data-testid="model-upgrade-technical">
        <summary className="flex cursor-pointer flex-wrap items-center gap-x-2 gap-y-1 p-3 text-sm font-medium text-text-pg">
          <span>{copy.preview.technicalTitle}</span>
          <span className="text-[10px] font-normal uppercase tracking-[0.1em] text-text-pg-dim">{copy.preview.technicalHint}</span>
        </summary>
        <div className="border-t border-border-pg p-4">
          <dl className="space-y-3">
            <DataRow label={copy.preview.modelIdLabel} value={FLASH_MODEL_ID} />
            <DataRow label={copy.preview.upstreamLabel} value={model?.provider_model_id || FLASH_MODEL_ID} />
            <DataRow label={copy.preview.contextLabel} value={contextWindow ?? copy.preview.contextUnavailable} />
            <DataRow
              label={`${copy.preview.priceLabel} (${copy.preview.inputLabel} / ${copy.preview.outputLabel})`}
              value={priceReviewed && input && output ? `${symbol}${input.amount} / ${symbol}${output.amount} ${copy.preview.perMillion}` : copy.preview.priceUnavailable}
            />
            {alias ? <DataRow label={copy.preview.aliasTitle} value={FLASH_ALIAS_ID} /> : null}
          </dl>
          {alias ? (
            <p className="mt-2 text-[11px] leading-5 text-text-pg-dim">
              {copy.preview.aliasBody.replace("{alias}", FLASH_ALIAS_ID).replace("{canonical}", FLASH_MODEL_ID)}
            </p>
          ) : null}
          <div className="mt-4 border border-border-pg bg-bg-app rounded-xl">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-pg px-3 py-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-pg-dim">{copy.preview.demoTitle}</span>
              <button
                type="button"
                onClick={() => void copyValue("request", sampleRequest)}
                className="inline-flex min-h-9 items-center gap-1.5 border border-border-pg px-2.5 py-1.5 text-xs text-text-pg-muted transition hover:border-border-pg-strong hover:text-text-pg rounded-lg"
              >
                {copied === "request" ? <Check className="h-3.5 w-3.5 text-status-positive" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
                {copied === "request" ? copy.preview.copied : copy.preview.copy}
              </button>
            </div>
            <pre className="touch-pan-x overflow-x-auto overscroll-x-contain p-3 text-[11px] leading-5 text-text-pg"><code>{sampleRequest}</code></pre>
          </div>
          <p className="mt-2 text-xs leading-5 text-text-pg-dim">{copy.preview.demoNote}</p>
          <p className="mt-2 text-xs leading-5 text-text-pg-dim">{copy.preview.technicalNote}</p>
        </div>
      </details>
    </section>
  );
}
