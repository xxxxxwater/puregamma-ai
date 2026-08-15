import clsx from "clsx";
import Link from "next/link";
import type { HTMLAttributes, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { AlertTriangle, CheckCircle2, Circle, Clock, Radio, ShieldAlert } from "lucide-react";
import { NavHistoryChart } from "@/components/charts";
import { formatCurrency, formatPercent } from "@/lib/formatters";
import { defaultLocale, type Locale } from "@/i18n/routing";
import { t } from "@/lib/translations";

export type Tone = "neutral" | "info" | "cyan" | "emerald" | "amber" | "red";
export type RiskLevel = "Low" | "Medium" | "High" | "Extreme";

export type PositionRow = {
  asset: string;
  source: string;
  quantity: string;
  price: number;
  value: number;
  costBasis: number;
  pnl: number;
  risk: "Low" | "Medium" | "High";
};

export type SignalRow = {
  id: string;
  asset: string;
  direction: string;
  signal_type: string;
  confidence: number;
  risk_score: number;
  thesis: string;
  catalyst: string;
  invalidation: string;
  timeframe: string;
  created_at?: string;
};

export type StrategyRow = {
  strategy_name: string;
  asset: string;
  risk_score: number;
  confidence: number;
  thesis: string;
  trigger: string;
  invalidation: string;
  timeframe: string;
  expected_payoff?: string;
};

export type IntegrationRow = {
  name: string;
  description: string;
  status: string;
  plan: string;
  cost: number;
  lastSync: string;
  failureReason?: string;
};

export function PGResearchCard({ children, className = "", ...props }: HTMLAttributes<HTMLElement> & { children: ReactNode; className?: string }) {
  return (
    <section className={clsx("min-w-0 border border-border-pg bg-bg-panel p-4 text-text-pg transition hover:border-border-pg-strong rounded-xl", className)} {...props}>
      {children}
    </section>
  );
}

export const ResearchCard = PGResearchCard;

export function PageHeader({
  eyebrow,
  title,
  description,
  subtitle,
  actions,
  sectionNumber
}: {
  eyebrow: string;
  title: string;
  description?: string;
  subtitle?: string;
  actions?: ReactNode;
  sectionNumber?: string;
}) {
  const body = description || subtitle;
  return (
    <div className="mb-8 border-b border-border-pg pb-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-4xl">
          <div className="mb-3 flex items-center gap-3 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">
            {sectionNumber ? <span className="text-text-pg">{sectionNumber}</span> : null}
            <span>{eyebrow}</span>
          </div>
          <h1 className="max-w-5xl text-2xl font-semibold tracking-normal text-text-pg">{title}</h1>
          {body ? <p className="mt-4 max-w-3xl text-sm leading-6 text-text-pg-muted">{body}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  delta,
  status,
  footnote,
  tone = "neutral",
  icon
}: {
  label: string;
  value: string;
  detail?: string;
  delta?: string;
  status?: Tone;
  footnote?: string;
  tone?: Tone;
  icon?: ReactNode;
}) {
  const displayTone = status ?? tone;
  return (
    <PGResearchCard>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{label}</span>
        <span className={toneClass(displayTone)}>{icon || <StatusDot tone={displayTone} />}</span>
      </div>
      <div className="mt-4 flex items-end gap-3">
        <div className="text-2xl font-semibold text-text-pg">{value}</div>
        {delta ? <div className={clsx("pb-1 text-xs", toneClass(displayTone))}>{delta}</div> : null}
      </div>
      {detail ? <p className="mt-2 text-sm text-text-pg-muted">{detail}</p> : null}
      {footnote ? <p className="mt-3 border-t border-border-pg pt-2 text-xs text-text-pg-dim">{footnote}</p> : null}
    </PGResearchCard>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return <span className={clsx("inline-flex items-center gap-1 border px-2 py-0.5 text-xs font-medium rounded-lg", badgeClass(tone))}>{children}</span>;
}

export function StatusDot({ tone = "neutral" }: { tone?: Tone }) {
  return <span className={clsx("inline-block h-1.5 w-1.5 rounded-full", dotClass(tone))} />;
}

export function StatCell({ label, value, dim = false }: { label: string; value: string; dim?: boolean }) {
  return <div className="bg-bg-panel p-4"><p className={dim ? "text-xs text-text-pg-dim" : "text-xs text-text-pg-muted"}>{label}</p><p className="mt-2 font-semibold">{value}</p></div>;
}

export function SignalBadge({ direction }: { direction: string }) {
  const normalized = direction.toLowerCase();
  const tone: Tone = normalized.includes("bear") || normalized.includes("short") ? "red" : normalized.includes("long") || normalized.includes("bull") ? "emerald" : "info";
  return (
    <Badge tone="neutral">
      <StatusDot tone={tone} />
      {direction}
    </Badge>
  );
}

export function RiskBadge({ score, level, locale = defaultLocale }: { score?: number; level?: RiskLevel; locale?: Locale }) {
  const resolvedLevel: RiskLevel = level || (score === undefined ? "Medium" : score >= 85 ? "Extreme" : score >= 70 ? "High" : score >= 50 ? "Medium" : "Low");
  const tone: Tone = resolvedLevel === "Extreme" || resolvedLevel === "High" ? "red" : resolvedLevel === "Medium" ? "amber" : "emerald";
  const riskLabel = t(locale, "common.risk.label");
  const levelLabel = t(locale, `common.risk.${resolvedLevel.toLowerCase()}` as "common.risk.low" | "common.risk.medium" | "common.risk.high" | "common.risk.extreme");
  return (
    <Badge tone="neutral">
      <StatusDot tone={tone} />
      {score !== undefined ? `${riskLabel} ${score}` : levelLabel}
    </Badge>
  );
}

export function DataSourceStatusBadge({ status, locale = defaultLocale }: { status: string; locale?: Locale }) {
  const normalized = status.toLowerCase();
  const tone: Tone = normalized.includes("error") || normalized.includes("failed") || normalized.includes("down") ? "red" : normalized.includes("need") || normalized.includes("license") || normalized.includes("degraded") || normalized.includes("partial") || normalized.includes("disabled") || normalized.includes("rate") || normalized.includes("delayed") || normalized.includes("warn") || normalized.includes("stale") || normalized.includes("requires") ? "amber" : normalized.includes("mock") ? "info" : "emerald";
  return (
    <Badge tone="neutral">
      <StatusDot tone={tone} />
      {localizedStatus(status, locale)}
    </Badge>
  );
}

export function CreditCostBadge({ cost, locale = defaultLocale }: { cost: number; locale?: Locale }) {
  return <Badge tone="neutral">{t(locale, "common.shared.creditCost", { credits: cost })}</Badge>;
}

type PlanIdentity = "silver" | "gold" | "black-gold" | "prestige";

const planIdentityStyles: Record<PlanIdentity, string> = {
  silver: "border-[var(--muted-2)] bg-[var(--muted-2)]/10 text-[var(--muted)]",
  gold: "border-[var(--warning)] bg-[var(--warning)]/10 text-[var(--warning)]",
  "black-gold": "border-[var(--warning)] bg-[var(--panel-strong)] text-[var(--warning)]",
  prestige: "border-[var(--info)] bg-[var(--info)]/10 text-[var(--info)]",
};

function planIdentity(plan: string): PlanIdentity {
  if (plan === "Enterprise") return "prestige";
  if (plan === "Max") return "black-gold";
  if (plan === "Pro") return "gold";
  return "silver";
}

function tierIdentity(tier: string): PlanIdentity {
  if (tier === "prestige") return "prestige";
  if (tier === "black-gold" || tier === "black_gold") return "black-gold";
  if (tier === "gold") return "gold";
  return "silver";
}

function PlanIdentityIcon({ identity }: { identity: PlanIdentity }) {
  if (identity === "prestige") {
    return <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m4 17 2-9 6 5 6-5 2 9H4Z" /><path d="M7 20h10M9 6l3-3 3 3-3 3-3-3Z" /></svg>;
  }
  if (identity === "black-gold") {
    return <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 2 20 6v6c0 5-3.4 8.2-8 10-4.6-1.8-8-5-8-10V6l8-4Z" /><path d="m7.5 14 1-5 3.5 3 3.5-3 1 5h-9ZM9 17h6" /></svg>;
  }
  if (identity === "gold") {
    return <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m12 2 8 5v10l-8 5-8-5V7l8-5Z" /><path d="m12 6 4 6-4 6-4-6 4-6Z" /></svg>;
  }
  return <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 2 20 6v6c0 5-3.4 8.2-8 10-4.6-1.8-8-5-8-10V6l8-4Z" /><path d="M8 9h8M8 12h8M10 15h4" /></svg>;
}

export function PlanBadge({ plan, tier, locale = defaultLocale }: { plan: string; tier?: string | null; locale?: Locale }) {
  const identity = tier ? tierIdentity(tier) : planIdentity(plan);
  const labels: Record<PlanIdentity, string> = locale === "zh"
    ? { silver: "白银", gold: "黄金", "black-gold": "黑金", prestige: "尊贵" }
    : { silver: "Silver", gold: "Gold", "black-gold": "Black Gold", prestige: "Prestige" };
  return (
    <span title={`${plan} · ${labels[identity]}`} className={clsx("inline-flex items-center gap-1.5 border px-2 py-0.5 text-xs font-semibold rounded-lg", planIdentityStyles[identity])}>
      <PlanIdentityIcon identity={identity} />
      <span>{plan}</span>
      <span className="font-normal opacity-75">· {labels[identity]}</span>
    </span>
  );
}

export function MockModeBadge({ live = false, locale = defaultLocale }: { live?: boolean; locale?: Locale }) {
  return (
    <Badge tone="neutral">
      <StatusDot tone={live ? "emerald" : "amber"} />
      {live ? t(locale, "common.badges.liveMode") : t(locale, "common.badges.mockMode")}
    </Badge>
  );
}

export function MarketRegimeBanner({ regime, freshness, summary, locale = defaultLocale }: { regime: string; freshness: string; summary: string; locale?: Locale }) {
  return (
    <section className="border border-border-pg bg-bg-panel p-5 rounded-xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">01 / {t(locale, "common.shared.marketRegime")}</div>
          <h2 className="mt-3 text-2xl font-semibold text-text-pg">{regime}</h2>
        </div>
        <Badge tone="neutral"><Radio className="h-3 w-3" /> {freshness}</Badge>
      </div>
      <p className="mt-5 max-w-4xl border-t border-border-pg pt-4 text-sm leading-6 text-text-pg-muted">{summary}</p>
    </section>
  );
}

export function PortfolioNavCard({ nav, pnlUsd, pnlPct, partial, locale = defaultLocale }: { nav: number; pnlUsd: number; pnlPct: number; partial?: boolean; locale?: Locale }) {
  return (
    <PGResearchCard className="md:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">02 / {t(locale, "common.shared.portfolioNAV")}</div>
          <div className="mt-4 text-4xl font-semibold">{formatCurrency(locale, nav)}</div>
          <div className={clsx("mt-2 text-sm", pnlUsd >= 0 ? "text-status-positive" : "text-status-negative")}>{formatCurrency(locale, pnlUsd)} / {formatPercent(locale, pnlPct)}</div>
        </div>
        {partial ? <Badge tone="neutral"><StatusDot tone="amber" /> {t(locale, "common.shared.partialData")}</Badge> : <Badge tone="neutral"><CheckCircle2 className="h-3 w-3" /> {t(locale, "common.shared.synced")}</Badge>}
      </div>
      {partial ? <p className="mt-4 border-t border-border-pg pt-3 text-sm text-status-warning">{t(locale, "portfolio.warning")}</p> : null}
    </PGResearchCard>
  );
}

export function NAVCurveCard({ title, data, locale = defaultLocale }: { title: string; data: { date: string; nav: number }[]; locale?: Locale }) {
  return (
    <PGResearchCard>
      <div className="mb-4 flex items-center justify-between border-b border-border-pg pb-3">
        <h2 className="font-semibold">{title}</h2>
        <Badge tone="neutral">{t(locale, "common.shared.netValueCurve")}</Badge>
      </div>
      <NavHistoryChart data={data} />
      <p className="mt-3 text-xs text-text-pg-dim">{t(locale, "compliance.backtest")}</p>
    </PGResearchCard>
  );
}

export function AllocationTable({ rows, locale = defaultLocale }: { rows: { name: string; weight: number; value: number }[]; locale?: Locale }) {
  return (
    <div className="divide-y divide-border-pg border border-border-pg rounded-xl overflow-hidden">
      {rows.map((row) => (
        <div key={row.name} className="grid grid-cols-[1fr_auto_auto] gap-3 px-3 py-2 text-sm">
          <span>{row.name}</span>
          <span className="text-text-pg-muted">{row.weight}%</span>
          <span>{formatCurrency(locale, row.value, true)}</span>
        </div>
      ))}
    </div>
  );
}

export function PositionsTable({ rows, locale = defaultLocale }: { rows: PositionRow[]; locale?: Locale }) {
  const headers = ["asset", "source", "qty", "price", "value", "costBasis", "unrealizedPnl", "risk"] as const;
  return (
    <div className="overflow-x-auto border border-border-pg rounded-xl">
      <table className="w-full min-w-[860px] text-sm">
        <thead className="text-left text-xs uppercase tracking-[0.12em] text-text-pg-muted">
          <tr>{headers.map((h) => <th key={h} className="border-b border-border-pg px-3 py-2 font-medium">{t(locale, `portfolio.tables.${h}`)}</th>)}</tr>
        </thead>
        <tbody>{rows.map((row) => <tr key={`${row.asset}-${row.source}`} className="border-b border-border-pg align-top last:border-0"><td className="px-3 py-3 font-semibold">{row.asset}</td><td className="px-3 py-3 text-text-pg-muted">{row.source}</td><td className="px-3 py-3">{row.quantity}</td><td className="px-3 py-3">{formatCurrency(locale, row.price)}</td><td className="px-3 py-3">{formatCurrency(locale, row.value)}</td><td className="px-3 py-3">{formatCurrency(locale, row.costBasis)}</td><td className={clsx("px-3 py-3", row.pnl >= 0 ? "text-status-positive" : "text-status-negative")}>{formatCurrency(locale, row.pnl)}</td><td className="px-3 py-3"><RiskBadge locale={locale} level={row.risk} /></td></tr>)}</tbody>
      </table>
    </div>
  );
}

export function SignalTable({ rows, locale = defaultLocale }: { rows: SignalRow[]; locale?: Locale }) {
  const headers = ["id", "asset", "signalType", "direction", "confidence", "risk", "catalyst", "invalidation", "timeframe", "source"] as const;
  return (
    <div className="max-w-full overflow-x-auto border border-border-pg rounded-xl">
      <table className="w-full min-w-[1060px] text-sm">
        <thead className="text-left text-xs uppercase tracking-[0.12em] text-text-pg-muted">
          <tr>{headers.map((h) => <th key={h} className="border-b border-border-pg px-3 py-2 font-medium">{t(locale, `signals.table.${h}`)}</th>)}</tr>
        </thead>
        <tbody>{rows.map((row, index) => <tr key={row.id} className="border-b border-border-pg align-top last:border-0"><td className="px-3 py-3 text-text-pg-dim">{String(index + 1).padStart(2, "0")}</td><td className="px-3 py-3 font-semibold">{row.asset}</td><td className="px-3 py-3 text-text-pg-muted">{row.signal_type}</td><td className="px-3 py-3"><SignalBadge direction={row.direction} /></td><td className="px-3 py-3">{Math.round(row.confidence * 100)}%</td><td className="px-3 py-3"><RiskBadge locale={locale} score={row.risk_score} /></td><td className="max-w-xs px-3 py-3 text-text-pg-muted">{row.catalyst}</td><td className="max-w-xs px-3 py-3 text-text-pg-muted">{row.invalidation}</td><td className="px-3 py-3">{row.timeframe}</td><td className="px-3 py-3 text-text-pg-muted">{t(locale, "common.shared.sharedIntelligence")}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

export function StrategyCard({ item, locale = defaultLocale }: { item: StrategyRow; locale?: Locale }) {
  return (
    <PGResearchCard>
      <div className="flex items-start justify-between gap-3 border-b border-border-pg pb-3">
        <div><h3 className="font-semibold">{item.strategy_name}</h3><p className="mt-1 text-sm text-text-pg-muted">{item.asset} / {item.timeframe}</p></div>
        <RiskBadge locale={locale} score={item.risk_score} />
      </div>
      <p className="mt-4 text-sm leading-6 text-text-pg-muted">{item.thesis}</p>
      <div className="mt-4 space-y-2 border-t border-border-pg pt-3 text-sm"><p><span className="text-text-pg-muted">{t(locale, "playbooks.labels.trigger")}:</span> {item.trigger}</p><p><span className="text-text-pg-muted">{t(locale, "playbooks.labels.invalidation")}:</span> {item.invalidation}</p></div>
    </PGResearchCard>
  );
}

export function BacktestResultCard({ metrics, locale = defaultLocale }: { metrics: { label: string; value: string }[]; locale?: Locale }) {
  return <PGResearchCard><h3 className="mb-3 font-semibold">{t(locale, "nautilus.modules.backtestResults")}</h3><div className="grid grid-cols-2 gap-px border border-border-pg bg-border-pg text-sm md:grid-cols-4 rounded-xl overflow-hidden">{metrics.map((metric) => <div key={metric.label} className="bg-bg-panel p-3"><div className="text-text-pg-muted">{metric.label}</div><div className="mt-1 text-lg font-semibold">{metric.value}</div></div>)}</div><p className="mt-3 text-xs text-text-pg-dim">{t(locale, "compliance.backtestShort")}</p></PGResearchCard>;
}

export function DailyBriefPreview({ locale = defaultLocale }: { locale?: Locale }) {
  return (
    <PGResearchCard>
      <div className="mx-auto max-w-sm border border-border-pg bg-bg-app p-4 rounded-xl">
        <div className="text-xs uppercase tracking-[0.14em] text-text-pg-muted">{t(locale, "daily-push.preview.label")}</div>
        <div className="mt-4 whitespace-pre-line border border-border-pg bg-bg-panel-muted p-4 text-sm leading-6 rounded-xl">
          {t(locale, "daily-push.preview.message")}
        </div>
      </div>
    </PGResearchCard>
  );
}

export const DailyPushPreview = DailyBriefPreview;

export function IntegrationConnectorCard({ item, locale = defaultLocale, manageHref }: { item: IntegrationRow; locale?: Locale; manageHref?: string }) {
  const manage = manageHref ?? (locale === "zh" ? "/zh/portfolio" : "/en/portfolio");
  return (
    <PGResearchCard>
      <div className="flex items-start justify-between gap-3 border-b border-border-pg pb-3"><div><h3 className="font-semibold">{item.name}</h3><p className="mt-1 text-sm text-text-pg-muted">{item.description}</p></div><DataSourceStatusBadge locale={locale} status={item.status} /></div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm"><span className="text-text-pg-muted">{t(locale, "integrations.cardLabels.requiredPlan")}</span><PlanBadge plan={item.plan} /><span className="text-text-pg-muted">{t(locale, "integrations.cardLabels.creditCost")}</span><CreditCostBadge locale={locale} cost={item.cost} /><span className="text-text-pg-muted">{t(locale, "integrations.cardLabels.lastSync")}</span><span>{item.lastSync}</span></div>
      {item.failureReason ? <p className="mt-3 text-sm text-status-warning">{item.failureReason}</p> : null}
      <div className="mt-4 flex gap-2"><a href={manage} className="border border-border-pg px-3 py-2 text-sm transition hover:border-border-pg-strong rounded-lg">{t(locale, "common.actions.connect")}</a><a href={manage} className="border border-border-pg px-3 py-2 text-sm transition hover:border-border-pg-strong rounded-lg">{t(locale, "common.actions.sync")}</a></div>
    </PGResearchCard>
  );
}

export function DiligenceLedger({ items, locale = defaultLocale }: { items: { label: string; status: string; detail: string }[]; locale?: Locale }) {
  return (
    <PGResearchCard>
      <div className="mb-4 border-b border-border-pg pb-3">
        <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-pg-muted">{t(locale, "dashboard.sections.diligenceLedger")}</div>
        <h3 className="mt-2 font-semibold">{locale === "zh" ? "验证记录" : "Verification record"}</h3>
      </div>
      <div className="divide-y divide-border-pg">
        {items.map((item, index) => (
          <div key={item.label} className="grid gap-3 py-3 text-sm md:grid-cols-[48px_1fr_auto]">
            <span className="text-text-pg-dim">{String(index + 1).padStart(2, "0")}</span>
            <div><div className="font-medium">{item.label}</div><div className="mt-1 text-text-pg-muted">{item.detail}</div></div>
            <DataSourceStatusBadge locale={locale} status={item.status} />
          </div>
        ))}
      </div>
    </PGResearchCard>
  );
}

export function ProcessStepper({ steps }: { steps: { label: string; detail: string }[] }) {
  return (
    <div className="grid gap-px border border-border-pg bg-border-pg md:grid-cols-4 rounded-xl overflow-hidden">
      {steps.map((step, index) => (
        <div key={step.label} className="bg-bg-panel p-4">
          <div className="text-xs text-text-pg-dim">{String(index + 1).padStart(2, "0")}</div>
          <div className="mt-3 font-semibold">{step.label}</div>
          <p className="mt-2 text-sm leading-5 text-text-pg-muted">{step.detail}</p>
        </div>
      ))}
    </div>
  );
}

export function ReportMarkdown({ content, locale = defaultLocale }: { content: string; locale?: Locale }) {
  return (
    <article className="pg-report prose prose-invert max-w-none text-sm leading-7 prose-headings:text-text-pg prose-p:text-text-pg-muted prose-li:text-text-pg-muted prose-strong:text-text-pg">
      <ReactMarkdown>{content}</ReactMarkdown>
    </article>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="border border-dashed border-border-pg bg-bg-panel p-8 text-center rounded-2xl"><Clock className="mx-auto h-6 w-6 text-text-pg-muted" /><h3 className="mt-3 font-semibold">{title}</h3><p className="mt-2 text-sm text-text-pg-muted">{description}</p></div>;
}

export function LoadingSkeleton() {
  return <div className="animate-pulse space-y-3"><div className="h-5 w-1/3 bg-bg-panel-muted" /><div className="h-32 border border-border-pg bg-bg-panel-muted rounded-xl" /><div className="h-32 border border-border-pg bg-bg-panel-muted rounded-xl" /></div>;
}

export function ErrorState({ title, description }: { title: string; description: string }) {
  return <div className="border border-border-pg-strong bg-bg-panel p-4 rounded-xl"><div className="flex gap-2 text-status-negative"><ShieldAlert className="h-5 w-5" /><strong>{title}</strong></div><p className="mt-2 text-sm text-text-pg-muted">{description}</p></div>;
}

export function ActionLink({ href, children }: { href: string; children: ReactNode }) {
  return <Link href={href} className="inline-flex items-center border border-border-pg px-3 py-2 text-sm font-medium hover:border-border-pg-strong hover:bg-bg-panel-muted rounded-lg">{children}</Link>;
}

function badgeClass(tone: Tone) {
  return {
    neutral: "border-border-pg bg-bg-panel-muted text-text-pg-muted",
    info: "border-border-pg-strong bg-bg-panel text-text-pg",
    cyan: "border-border-pg-strong bg-bg-panel text-text-pg",
    emerald: "border-border-pg bg-bg-panel text-status-positive",
    amber: "border-border-pg bg-bg-panel text-status-warning",
    red: "border-border-pg bg-bg-panel text-status-negative"
  }[tone];
}

function dotClass(tone: Tone) {
  return {
    neutral: "bg-text-pg-dim",
    info: "bg-text-pg",
    cyan: "bg-text-pg",
    emerald: "bg-status-positive",
    amber: "bg-status-warning",
    red: "bg-status-negative"
  }[tone];
}

function toneClass(tone: Tone) {
  return { neutral: "text-text-pg-muted", info: "text-text-pg", cyan: "text-text-pg", emerald: "text-status-positive", amber: "text-status-warning", red: "text-status-negative" }[tone];
}

function localizedStatus(status: string, locale: Locale) {
  const normalized = status.toLowerCase();
  if (normalized === "healthy") return t(locale, "common.status.healthy");
  if (normalized === "delayed") return t(locale, "common.status.delayed");
  if (normalized === "mock") return t(locale, "common.status.mock");
  if (normalized === "warning") return t(locale, "common.status.warning");
  if (normalized === "available") return t(locale, "common.status.available");
  if (normalized === "processed") return t(locale, "common.status.processed");
  if (normalized === "pending") return t(locale, "common.status.pending");
  if (normalized === "idle") return t(locale, "common.status.idle");
  if (normalized === "sent") return t(locale, "common.status.sent");
  if (normalized === "skipped") return t(locale, "common.status.skipped");
  if (normalized.includes("requires key")) return t(locale, "common.status.requiresKey");
  if (normalized.includes("stale warning")) return t(locale, "common.status.staleWarning");
  return status;
}
