import Image from "next/image";
import type { Locale } from "@/i18n/routing";

/** Quiet brand illustration for the landing page, shared with the SaaS design study. */
export function BrandOrbit({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  return (
    <div className="pg-brand-orbit" aria-label={zh ? "PureGamma 研究：信号、背景、决策" : "PureGamma research: signal, context, decision"} role="img">
      <span className="pg-brand-orbit__eyebrow">{zh ? "研究" : "RESEARCH"}</span>
      <span className="pg-brand-orbit__ring pg-brand-orbit__ring--outer" aria-hidden />
      <span className="pg-brand-orbit__ring pg-brand-orbit__ring--middle" aria-hidden />
      <span className="pg-brand-orbit__ring pg-brand-orbit__ring--inner" aria-hidden />
      <span className="pg-brand-orbit__mark" aria-hidden>
        <Image src="/logo.png" alt="" width={68} height={68} />
      </span>
      <span className="pg-brand-orbit__caption">{zh ? "信号 → 背景 → 决策" : "SIGNAL → CONTEXT → DECISION"}</span>
    </div>
  );
}
