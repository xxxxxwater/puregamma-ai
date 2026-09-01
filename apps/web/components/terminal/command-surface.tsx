"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, ScanSearch } from "lucide-react";
import { LiquidLens } from "@/components/terminal/liquid-lens";
import { withLocale, type Locale } from "@/i18n/routing";

const CHIPS = [
  { en: "Risk check", zh: "风险检查" },
  { en: "Research: BTC", zh: "研究：BTC" },
  { en: "Portfolio exposure", zh: "组合敞口" },
  { en: "Today brief", zh: "今日简报" },
];

/**
 * The primary AI work surface on the dashboard. Enter routes into the Agent
 * conversation (Chat); chips pre-write honest example prompts. Never a fake
 * capability — the destination is a real, existing workflow.
 */
export function CommandSurface({ locale }: { locale: Locale }) {
  const router = useRouter();
  const zh = locale === "zh";
  const [value, setValue] = useState("");

  const go = (q: string) => {
    router.push(withLocale(locale, q.trim() ? `/chat?prompt=${encodeURIComponent(q.trim())}` : "/chat"));
  };

  const submit = (e: FormEvent) => { e.preventDefault(); go(value); };

  return (
    <LiquidLens className="command-surface">
      <form onSubmit={submit} className="flex items-center gap-3">
        <ScanSearch className="h-4 w-4 shrink-0 text-accent" aria-hidden />
        <input value={value} onChange={(e) => setValue(e.target.value)}
          placeholder={zh ? "向 PureGamma 询问市场、你的组合或一个风险情景……" : "Ask PureGamma about the market, your portfolio, or a risk scenario…"}
          className="command-input" aria-label={zh ? "向 PureGamma 提问" : "Ask PureGamma"} />
        <button type="submit" className="command-submit" aria-label={zh ? "打开对话" : "Open a conversation"}><span className="command-submit-label">{zh ? "开始" : "Start"}</span><ArrowUpRight className="h-3.5 w-3.5" aria-hidden /></button>
      </form>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {CHIPS.map((chip) => (
          <button key={chip.en} type="button" className="command-chip" onClick={() => go(chip.en)}>
            {zh ? chip.zh : chip.en}
          </button>
        ))}
      </div>
    </LiquidLens>
  );
}
