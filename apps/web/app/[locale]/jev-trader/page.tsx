import type { Metadata } from "next";

import { JevTraderConsole } from "@/components/jev-trader-console";
import { PageHeader } from "@/components/puregamma";
import { isLocale, type Locale } from "@/i18n/routing";

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return {
    title: "Jev Trader — PureGamma AI",
    description:
      locale === "zh"
        ? "第三方 Jev Trader 实时展示：真实链上行情与模型决策，模拟交易，无真实资金。"
        : "Live third-party Jev Trader view: real on-chain prices and model decisions, simulated trading, no real funds.",
  };
}

export default function JevTraderPage({ params }: { params: { locale: Locale } }) {
  const zh = params.locale === "zh";
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="TypeSafe Jev"
        title="Jev Trader"
        description={
          zh
            ? "实时模型决策看板。行情为真实 Monad 链上数据，模型为真实 Jev 推理，交易为模拟。"
            : "A real-time model decision dashboard. Prices are real Monad on-chain data, inference is real Jev, trading is simulated."
        }
        sectionNumber="11"
      />
      <JevTraderConsole locale={params.locale} />
    </div>
  );
}
