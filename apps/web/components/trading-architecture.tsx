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
  const ring = accent ? "border-border-pg-strong" : "border-border-pg";
  return (
    <div data-testid="architecture-node" className={`architecture-node absolute z-10 w-[70px] -translate-x-1/2 -translate-y-1/2 border ${ring} bg-bg-panel-muted px-1 py-1 text-center rounded-lg ${className}`}>
      <div className="architecture-node-title whitespace-normal text-11 font-semibold leading-tight text-text-pg">{title}</div>
      {detail ? <div className="architecture-node-detail mt-0.5 whitespace-normal text-11 leading-tight text-text-pg-dim">{detail}</div> : null}
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
        stroke={light ? "var(--muted-2)" : "currentColor"}
        strokeOpacity={light ? 0.18 : 0.4}
        strokeWidth={light ? 0.35 : 0.5}
        vectorEffect="non-scaling-stroke"
        strokeDasharray="1.5 1.5"
        className="pg-flow-dash"
      />
      <circle r="1.15" fill="var(--foreground)" opacity="0.65">
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
    // Kept short: this label sits in a fixed-width SVG node and must not clip.
    gatewayDetail: "V4.1 Flash · Kimi · GLM · Luna",
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
    runtimeMap: zh ? "PureGamma 运行图" : "PureGamma Runtime Map",
    signedTopology: zh ? "HMAC 签名拓扑" : "HMAC signed topology",
    live: zh ? "系统示意" : "SYSTEM MAP",
    windowControls: zh ? "macOS 窗口控制" : "macOS window controls",
    closePreview: zh ? "关闭架构预览" : "Close architecture preview",
    minimizePreview: zh ? "最小化架构预览" : "Minimize architecture preview",
    expandPreview: zh ? "展开架构预览" : "Expand architecture preview",
  };

  return (
    <section className="relative overflow-hidden rounded-3xl border border-border-pg bg-bg-panel p-6 shadow-panel md:p-9">
      <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">{copy.eyebrow}</div>
      <h2 className="mt-2 max-w-2xl text-lg font-semibold text-text-pg">{copy.headline}</h2>

      <div
        data-testid="architecture-mac-window"
        className="relative mx-auto mt-7 max-w-4xl rounded-[30px] border-[7px] border-border-pg bg-bg-panel-muted p-1.5 shadow-card"
      >
        <div className="pointer-events-none absolute left-1/2 top-0 z-30 h-4 w-24 -translate-x-1/2 rounded-b-[10px] bg-border-pg" aria-hidden />
        <div className="overflow-hidden rounded-[21px] border border-border-pg bg-bg-panel">
          <div className="flex h-9 items-center justify-between border-b border-border-pg bg-bg-panel px-3 text-11 text-text-pg-muted">
            <div className="flex items-center gap-1.5" aria-label={copy.windowControls}>
              <span role="img" aria-label={copy.closePreview} className="h-2.5 w-2.5 rounded-full bg-border-pg-strong" />
              <span role="img" aria-label={copy.minimizePreview} className="h-2.5 w-2.5 rounded-full bg-border-pg-strong" />
              <span role="img" aria-label={copy.expandPreview} className="h-2.5 w-2.5 rounded-full bg-border-pg-strong" />
            </div>
            <div className="absolute left-1/2 flex -translate-x-1/2 items-center gap-2 font-medium tracking-[0.08em] text-text-pg-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.9)]" />
              <span>PUREGAMMA.AI</span>
            </div>
            <div className="rounded-full border border-border-pg bg-bg-panel-muted px-2 py-0.5 font-semibold tracking-[0.12em] text-text-pg-muted">{copy.live}</div>
          </div>

          <div data-testid="architecture-system-map" className="architecture-system-map relative h-[520px] w-full overflow-hidden bg-bg-panel-muted/40">
            <div data-testid="architecture-map-caption" className="absolute bottom-2 left-2 z-20 rounded-md border border-border-pg bg-bg-panel px-2 py-1 text-11 uppercase tracking-[0.14em] text-text-pg-muted backdrop-blur-sm">
              <span className="font-semibold">{copy.runtimeMap}</span>
              <span className="ml-2 text-text-pg-dim">{copy.signedTopology}</span>
            </div>
        {/* Flow layer */}
        <svg
          className="absolute inset-0 h-full w-full text-text-pg-muted"
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
        <NodeCard title={copy.user} className="architecture-user left-[50%] top-[6%]" />
        <NodeCard title={copy.web} className="architecture-web left-[21%] top-[17%]" />
        <NodeCard title={copy.ios} className="architecture-ios left-[50%] top-[18%]" />
        <NodeCard title={copy.android} className="architecture-android left-[79%] top-[17%]" />
        <NodeCard title={copy.api} accent="emerald" className="architecture-api left-[50%] top-[29%] px-1.5 py-1" />
        <NodeCard title={copy.auth} detail={copy.authDetail} className="architecture-auth left-[15%] top-[41%]" />
        <NodeCard title={copy.agent} detail={copy.agentDetail} className="architecture-agent left-[50%] top-[41%]" />
        <NodeCard title={copy.gateway} detail={copy.gatewayDetail} className="architecture-gateway left-[85%] top-[41%]" />
        <NodeCard title={copy.options} detail={copy.optionsDetail} className="architecture-options left-[15%] top-[52%]" />
        <NodeCard title={copy.backtest} className="architecture-backtest left-[50%] top-[52%]" />
        <NodeCard title={copy.research} detail={copy.researchDetail} className="architecture-research left-[85%] top-[52%]" />
        <NodeCard title={copy.skills} className="architecture-skills left-[15%] top-[63%]" />
        <NodeCard title={copy.portfolio} detail={copy.portfolioDetail} className="architecture-portfolio left-[50%] top-[63%]" />
        <NodeCard title={copy.data} detail={copy.dataDetail} className="architecture-data left-[85%] top-[63%]" />
        <NodeCard title={copy.trading} accent="blue" className="architecture-trading left-[30%] top-[78%] px-1.5 py-1" />
        <NodeCard title={copy.runtime} detail={copy.runtimeDetail} accent="emerald" className="architecture-runtime left-[70%] top-[78%] px-1.5 py-1" />
        <NodeCard title={copy.notify} detail={copy.notifyDetail} className="architecture-notify left-[50%] top-[88%]" />

        {/* HMAC label on the trading→runtime link */}
        <span className="absolute left-1/2 top-[75.5%] z-10 -translate-x-1/2 border border-border-pg bg-bg-panel px-1.5 py-0.5 text-11 font-semibold tracking-wide text-text-pg-dim rounded">
          {copy.hmac}
        </span>

        {/* Legend */}
        <div className="absolute bottom-2 right-2 flex items-center gap-3 rounded-md border border-border-pg/60 bg-bg-panel/90 px-2 py-1 text-11 text-text-pg-dim">
          <span className="flex items-center gap-1"><span className="h-1 w-3 rounded bg-current opacity-40" />{copy.legend}</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-text-pg-muted" />API</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-text-pg-muted" />Trading</span>
        </div>
          </div>
        </div>
        <div data-testid="architecture-mac-base" className="mx-auto h-2 w-[60%] rounded-b-[18px] border-x border-b border-border-pg bg-bg-panel-muted" aria-hidden />
      </div>
      <style jsx global>{`
        .architecture-system-map { container-type: inline-size; }
        @container (min-width: 640px) {
          .architecture-system-map { height: 520px !important; }
          .architecture-node { width: auto !important; padding: 0.375rem 0.5rem !important; }
          .architecture-node-title { white-space: nowrap !important; font-size: 0.58rem !important; }
          .architecture-node-detail { white-space: nowrap !important; font-size: 9px !important; }
          .architecture-api, .architecture-trading, .architecture-runtime { padding: 0.5rem 0.75rem !important; }
          .architecture-user { top: 6% !important; }
          .architecture-web { left: 21% !important; top: 17% !important; }
          .architecture-ios { top: 18% !important; }
          .architecture-android { left: 79% !important; top: 17% !important; }
          .architecture-api { top: 29% !important; }
          .architecture-auth, .architecture-agent, .architecture-gateway { top: 41% !important; }
          .architecture-options, .architecture-backtest, .architecture-research { top: 52% !important; }
          .architecture-trading, .architecture-runtime { top: 78% !important; }
          .architecture-notify { top: 92% !important; }
        }
      `}</style>
    </section>
  );
}
