"use client";

type Locale = "en" | "zh";

function NodeCard({
  title,
  detail,
  accent,
  className = "",
}: {
  title: string;
  detail?: string;
  accent?: "emerald" | "blue";
  className?: string;
}) {
  const ring =
    accent === "emerald"
      ? "border-status-positive/30"
      : accent === "blue"
        ? "border-sky-500/30"
        : "border-border-pg-strong";
  return (
    <div className={`absolute z-10 -translate-x-1/2 -translate-y-1/2 border ${ring} bg-bg-panel-muted px-2 py-1.5 text-center rounded-lg ${className}`}>
      <div className="whitespace-nowrap text-[0.58rem] font-semibold leading-tight text-text-pg">{title}</div>
      {detail ? <div className="mt-0.5 whitespace-nowrap text-[9px] leading-tight text-text-pg-dim">{detail}</div> : null}
    </div>
  );
}

function FlowPath({
  d,
  light = false,
  duration = 3,
}: {
  d: string;
  light?: boolean;
  duration?: number;
}) {
  return (
    <>
      <path
        d={d}
        fill="none"
        stroke={light ? "var(--text-pg, #9ca3af)" : "currentColor"}
        strokeOpacity={light ? 0.18 : 0.4}
        strokeWidth={light ? 0.35 : 0.5}
        vectorEffect="non-scaling-stroke"
        strokeDasharray="1.5 1.5"
        className="pg-flow-dash"
      />
      <circle r="1.15" fill={light ? "#f472b6" : "#34d399"} opacity="0.95">
        <animateMotion dur={`${duration}s`} repeatCount="indefinite" path={d} keyPoints="0;1" keyTimes="0;1" />
        <animate attributeName="opacity" values="0.95;0.35;0.95" dur="1.6s" repeatCount="indefinite" />
      </circle>
    </>
  );
}

const PATHS = {
  userWeb: "M 50 8 C 42 10, 30 12, 22 14.5",
  userIos: "M 50 8 L 50 15.5",
  userAndroid: "M 50 8 C 58 10, 70 12, 78 14.5",
  webApi: "M 22 18.5 C 30 21, 40 24, 47 26.5",
  iosApi: "M 50 20 L 50 26.5",
  androidApi: "M 78 18.5 C 70 21, 60 24, 53 26.5",
  apiAgent: "M 50 31 C 42 34, 36 37, 50 38.5",
  apiGateway: "M 50 31 C 58 34, 66 37, 83 38.5",
  apiTrading: "M 46 31 C 42 50, 38 62, 31 74.5",
  tradingRuntime: "M 34 78 L 66 78",
  apiNotify: "M 50 31 C 50 58, 50 72, 50 88.5",
};

export function TradingArchitecture({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const copy = {
    eyebrow: zh ? "PureGamma AI 系统架构" : "PureGamma AI System Architecture",
    headline: zh
      ? "从用户入口到研究、组合、风控与触达的完整链路，交易指令经 HMAC 签名进入隔离运行环境"
      : "The full pipeline from user entry to research, portfolio, risk, and delivery — trading commands reach an isolated runtime over HMAC-signed channels",
    user: zh ? "用户" : "User",
    web: "Web · Next.js",
    ios: "iOS · SwiftUI",
    android: "Android · Compose",
    api: "FastAPI API",
    auth: zh ? "身份 / 计费" : "Auth / Billing",
    authDetail: "Google · Apple · Email · Stripe",
    agent: zh ? "Agent + 私密秘书" : "Agent + Secretary",
    agentDetail: zh ? "会话 · 工具 · SSE" : "Chat · tools · SSE",
    gateway: "AI Gateway",
    gatewayDetail: "DeepSeek · Kimi · GLM · Luna",
    options: zh ? "期权研究" : "Options",
    optionsDetail: "Deribit · Polygon · Long Gamma",
    backtest: zh ? "回测实验室" : "Backtest Lab",
    research: zh ? "研究沙箱" : "Research Runner",
    researchDetail: zh ? "Docker 隔离" : "Docker sandbox",
    skills: zh ? "技能库" : "Skills",
    portfolio: "Portfolio NAV",
    portfolioDetail: "Plaid · IBKR · Hyperliquid",
    data: zh ? "数据源" : "Data",
    dataDetail: "RSS · FinTwit · X · 链上",
    trading: zh ? "交易控制面" : "Trading Control",
    runtime: "Nautilus Runtime",
    runtimeDetail: "PAPER / SHADOW / BACKTEST",
    notify: zh ? "通知分发" : "Notifications",
    notifyDetail: "Email · Telegram · Slack · APNs · iMessage",
    hmac: "HMAC",
    legend: zh ? "数据流" : "Data flow",
  };

  return (
    <div className="relative border border-border-pg bg-bg-panel p-5 md:p-7 rounded-2xl">
      <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">{copy.eyebrow}</div>
      <h2 className="mt-2 max-w-2xl text-lg font-semibold text-text-pg">{copy.headline}</h2>

      <div className="relative mt-6 h-[520px] w-full overflow-hidden rounded-xl border border-border-pg/60 bg-bg-panel-muted/40">
        {/* Flow layer */}
        <svg
          className="absolute inset-0 h-full w-full text-emerald-400/70"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          <FlowPath d={PATHS.userWeb} light />
          <FlowPath d={PATHS.userIos} />
          <FlowPath d={PATHS.userAndroid} light />
          <FlowPath d={PATHS.webApi} light />
          <FlowPath d={PATHS.iosApi} />
          <FlowPath d={PATHS.androidApi} light />
          <FlowPath d={PATHS.apiAgent} />
          <FlowPath d={PATHS.apiGateway} light />
          <FlowPath d={PATHS.apiTrading} duration={2.4} />
          <FlowPath d={PATHS.tradingRuntime} light duration={2.4} />
          <FlowPath d={PATHS.apiNotify} duration={4} />
        </svg>

        {/* Nodes */}
        <NodeCard title={copy.user} className="left-[50%] top-[6%]" />
        <NodeCard title={copy.web} className="left-[21%] top-[17%]" />
        <NodeCard title={copy.ios} className="left-[50%] top-[18%]" />
        <NodeCard title={copy.android} className="left-[79%] top-[17%]" />
        <NodeCard title={copy.api} accent="emerald" className="left-[50%] top-[29%] px-3 py-2" />
        <NodeCard title={copy.auth} detail={copy.authDetail} className="left-[15%] top-[41%]" />
        <NodeCard title={copy.agent} detail={copy.agentDetail} className="left-[50%] top-[41%]" />
        <NodeCard title={copy.gateway} detail={copy.gatewayDetail} className="left-[85%] top-[41%]" />
        <NodeCard title={copy.options} detail={copy.optionsDetail} className="left-[15%] top-[52%]" />
        <NodeCard title={copy.backtest} className="left-[50%] top-[52%]" />
        <NodeCard title={copy.research} detail={copy.researchDetail} className="left-[85%] top-[52%]" />
        <NodeCard title={copy.skills} className="left-[15%] top-[63%]" />
        <NodeCard title={copy.portfolio} detail={copy.portfolioDetail} className="left-[50%] top-[63%]" />
        <NodeCard title={copy.data} detail={copy.dataDetail} className="left-[85%] top-[63%]" />
        <NodeCard title={copy.trading} accent="blue" className="left-[30%] top-[78%] px-3 py-2" />
        <NodeCard title={copy.runtime} detail={copy.runtimeDetail} accent="emerald" className="left-[70%] top-[78%] px-3 py-2" />
        <NodeCard title={copy.notify} detail={copy.notifyDetail} className="left-[50%] top-[92%]" />

        {/* HMAC label on the trading→runtime link */}
        <span className="absolute left-1/2 top-[75.5%] z-10 -translate-x-1/2 border border-border-pg bg-bg-panel px-1.5 py-0.5 text-[8px] font-semibold tracking-wide text-text-pg-dim rounded">
          {copy.hmac}
        </span>

        {/* Legend */}
        <div className="absolute bottom-2 right-2 flex items-center gap-3 rounded-md border border-border-pg/60 bg-bg-panel/90 px-2 py-1 text-[8px] text-text-pg-dim">
          <span className="flex items-center gap-1"><span className="h-1 w-3 rounded bg-current opacity-40" />{copy.legend}</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />API</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-sky-400" />Trading</span>
        </div>
      </div>
    </div>
  );
}
