"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Info } from "lucide-react";
import { Badge } from "@/components/puregamma";
import { normalizeLocale, withLocale, type Locale } from "@/i18n/routing";
import { SelectionBox } from "@/components/selection-box";
import { getMessageNamespace, t } from "@/lib/translations";

export default function LocalizedOnboardingAssetsPage({ params }: { params: { locale: string } }) {
  const locale = normalizeLocale(params.locale);
  const router = useRouter();
  const copy = getMessageNamespace(locale, "onboarding").assets;
  const [selected, setSelected] = useState<Set<string>>(new Set(["BTC", "ETH", "SOL"]));

  const toggle = (symbol: string) => {
    const next = new Set(selected);
    if (next.has(symbol)) next.delete(symbol);
    else next.add(symbol);
    setSelected(next);
  };

  const handleContinue = () => {
    if (selected.size === 0) return;
    localStorage.setItem("pg_onboarding_assets", JSON.stringify([...selected]));
    router.push(withLocale(locale, "/onboarding/style"));
  };

  return (
    <div className="mx-auto max-w-3xl py-8">
      <div className="mb-8">
        <div className="flex items-center gap-3 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">
          <span>{copy.step}</span>
          <span className="text-text-pg">{copy.kicker}</span>
        </div>
        <h1 className="mt-4 text-3xl font-semibold">{copy.title}</h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-text-pg-muted">{copy.subtitle}</p>
        <div className="mt-4 flex gap-2">
          <button onClick={() => setSelected(new Set(copy.items.map((asset) => asset.symbol)))} className="border border-border-pg px-3 py-1.5 text-xs hover:border-border-pg-strong rounded-lg">
            {copy.selectAll}
          </button>
          <button onClick={() => setSelected(new Set())} className="border border-border-pg px-3 py-1.5 text-xs hover:border-border-pg-strong rounded-lg">
            {copy.clear}
          </button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {copy.items.map((asset) => {
          const isSelected = selected.has(asset.symbol);
          return (
            <button
              key={asset.symbol}
              onClick={() => toggle(asset.symbol)}
              className={`border p-5 text-left transition  rounded-xl${
                isSelected ? "border-border-pg-strong bg-bg-panel-muted" : "border-border-pg bg-bg-panel hover:border-border-pg-strong"
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-lg font-semibold">{asset.symbol}</span>
                    <Badge tone="neutral">{asset.category}</Badge>
                  </div>
                  <p className="mt-2 text-sm leading-5 text-text-pg-muted">{asset.description}</p>
                </div>
                <SelectionBox selected={isSelected} />
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-8 flex items-center justify-between gap-4 border border-border-pg bg-bg-panel-muted px-4 py-3 rounded-lg">
        <div className="flex items-center gap-2 text-sm text-text-pg-muted">
          <Info className="h-4 w-4 shrink-0" aria-hidden />
          {selectedLabel(locale, selected.size)}
        </div>
        <button
          onClick={handleContinue}
          disabled={selected.size === 0}
          className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-5 py-2.5 text-sm font-semibold text-pg-black transition hover:bg-pg-white-soft disabled:cursor-not-allowed disabled:opacity-40 rounded-lg"
        >
          {copy.continue} <ArrowRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}

function selectedLabel(locale: Locale, count: number): string {
  return t(locale, count === 1 ? "onboarding.assets.selectedSingular" : "onboarding.assets.selected", { count });
}


