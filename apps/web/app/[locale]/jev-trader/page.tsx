import { JevAdvisoryConsole } from "@/components/jev-advisory-console";
import type { Locale } from "@/i18n/routing";

export default function JevTraderPage({ params }: { params: { locale: Locale } }) {
  const zh = params.locale === "zh";
  return <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
    <div className="mb-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-text-pg-muted">Harness · TypeSafe JEV</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">{zh ? "Jev 顾问" : "Jev advisor"}</h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-text-pg-muted">
        {zh ? "用经验证的建议遥测替代不透明的第三方“实时交易演示”。" : "Validated advisory telemetry, replacing an opaque third-party live-trading demo."}
      </p>
    </div>
    <JevAdvisoryConsole locale={params.locale} />
  </main>;
}
