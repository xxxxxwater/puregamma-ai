"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Crosshair, Globe, Info, Shield, TrendingUp, Zap, type LucideIcon } from "lucide-react";
import { normalizeLocale, withLocale } from "@/i18n/routing";
import { SelectionBox } from "@/components/selection-box";
import { getMessageNamespace, t } from "@/lib/translations";

const styleIcons: Record<string, LucideIcon> = {
  "risk-controlled": Shield,
  momentum: TrendingUp,
  "macro-sensitive": Globe,
  "event-driven": Zap,
  "high-beta": Crosshair
};

export default function LocalizedOnboardingStylePage({ params }: { params: { locale: string } }) {
  const locale = normalizeLocale(params.locale);
  const router = useRouter();
  const copy = getMessageNamespace(locale, "onboarding").style;
  const [selected, setSelected] = useState("risk-controlled");

  const handleContinue = () => {
    localStorage.setItem("pg_onboarding_style", selected);
    router.push(withLocale(locale, "/onboarding/channels"));
  };

  const selectedStyle = copy.items.find((style) => style.id === selected) ?? copy.items[0];

  return (
    <div className="mx-auto max-w-3xl py-8">
      <div className="mb-8">
        <div className="flex items-center gap-3 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">
          <span>{copy.step}</span>
          <span className="text-text-pg">{copy.kicker}</span>
        </div>
        <h1 className="mt-4 text-3xl font-semibold">{copy.title}</h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-text-pg-muted">{copy.subtitle}</p>
      </div>

      <div className="space-y-3">
        {copy.items.map((style) => {
          const Icon = styleIcons[style.id] ?? Shield;
          const isSelected = selected === style.id;
          return (
            <button
              key={style.id}
              onClick={() => setSelected(style.id)}
              className={`w-full border p-5 text-left transition ${
                isSelected ? "border-border-pg-strong bg-bg-panel-muted" : "border-border-pg bg-bg-panel hover:border-border-pg-strong"
              }`}
            >
              <div className="flex items-start gap-4">
                <div className={`mt-0.5 border p-2.5 ${isSelected ? "border-border-pg-strong bg-bg-panel-muted" : "border-border-pg bg-bg-panel-muted"}`}>
                  <Icon className={`h-5 w-5 ${isSelected ? "text-text-pg" : "text-text-pg-muted"}`} aria-hidden />
                </div>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{style.label}</span>
                    <span className={`border border-border-pg px-2 py-0.5 text-[0.65rem] font-medium ${riskTone(style.id)}`}>{style.risk}</span>
                  </div>
                  <p className="mt-1.5 text-sm leading-5 text-text-pg-muted">{style.description}</p>
                </div>
                <SelectionBox selected={isSelected} />
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-8 flex items-center justify-between gap-4 border border-border-pg bg-bg-panel-muted px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-text-pg-muted">
          <Info className="h-4 w-4 shrink-0" aria-hidden />
          {t(locale, "onboarding.style.riskProfile", { label: selectedStyle.label, risk: selectedStyle.risk })}
        </div>
        <button onClick={handleContinue} className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-5 py-2.5 text-sm font-semibold text-pg-black transition hover:bg-pg-white-soft">
          {copy.continue} <ArrowRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}

function riskTone(id: string): string {
  if (id === "risk-controlled") return "text-status-positive";
  if (id === "momentum" || id === "macro-sensitive") return "text-status-warning";
  return "text-status-negative";
}


