import type { ReactNode } from "react";

type Locale = "en" | "zh";

function FlowNode({ title, items, accent }: { title: string; items: string[]; accent?: "blue" | "emerald" }) {
  const border = accent === "emerald" ? "border-status-positive/30" : "border-border-pg-strong";
  return (
    <div className={`border ${border} bg-bg-panel-muted p-3 rounded-lg`}>
      <div className="text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-text-pg-muted">{title}</div>
      <div className="mt-2 space-y-1">
        {items.map((item) => <div key={item} className="flex items-center gap-2 text-xs text-text-pg"><span className="h-1.5 w-1.5 shrink-0 rounded-full bg-status-positive/70" />{item}</div>)}
      </div>
    </div>
  );
}

function Bus({ children }: { children: ReactNode }) {
  return (
    <div className="relative overflow-hidden border border-border-pg bg-bg-panel-muted px-4 py-2 text-center rounded-lg">
      {/* flowing data pulses along the bus */}
      <div className="pointer-events-none absolute inset-y-0 w-10 bg-gradient-to-r from-transparent via-text-pg/25 to-transparent bus-flow" />
      <div className="text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-text-pg-muted">{children}</div>
    </div>
  );
}

function VerticalLink({ label }: { label?: string }) {
  return (
    <div className="relative mx-auto flex h-7 w-px flex-col items-center bg-border-pg-strong">
      <span className="absolute -left-1 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-text-pg/60 link-pulse" />
      {label ? <span className="absolute left-3 top-1/2 -translate-y-1/2 whitespace-nowrap text-[9px] text-text-pg-dim">{label}</span> : null}
    </div>
  );
}

export function TradingArchitecture({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const copy = {
    eyebrow: zh ? "为真实交易而构建" : "Engineered for real trading",
    headline: zh ? "同一套事件模型、时钟、缓存与执行流，回测与实盘完全一致" : "The same event model, clock, cache, and execution flow run in backtest and live environments",
    dataClients: zh ? "数据客户端" : "Data Clients",
    execClients: zh ? "执行客户端" : "Execution Clients",
    trader: zh ? "交易器" : "Trader",
    portfolio: zh ? "组合：持仓 · 保证金 · PnL" : "Portfolio — positions · margin · pnl",
    dataEngine: zh ? "数据引擎：订阅 · 请求" : "Data Engine — subscriptions · requests",
    strategyQuoter: zh ? "策略：做市" : "Strategy — quoter",
    strategyHedger: zh ? "策略：对冲" : "Strategy — hedger",
    execEngine: zh ? "执行引擎：订单指令" : "Exec Engine — order commands",
    riskEngine: zh ? "风控引擎：交易前后" : "Risk Engine — pre|post-trade",
    messageBus: zh ? "消息总线 · 发布/订阅 · 请求/响应 · 数据 · 指令 · 事件" : "Message Bus — pub/sub · req/res · data · commands · events",
    cache: zh ? "缓存：合约 · 订单 · 持仓 · 自定义" : "Cache — instruments · orders · positions · custom",
    database: zh ? "数据库 · 持久化" : "Database — persistence",
  };

  return (
    <div className="border border-border-pg bg-bg-panel p-5 md:p-7 rounded-2xl">
      <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">{copy.eyebrow}</div>
      <h2 className="mt-2 text-lg font-semibold text-text-pg">{copy.headline}</h2>

      <div className="mt-7 space-y-0">
        {/* Data / Execution clients feeding the Trader */}
        <div className="grid gap-6 md:grid-cols-2">
          <FlowNode title={copy.dataClients} items={["Databento", "OKX"]} />
          <FlowNode title={copy.execClients} items={["OKX", "Bybit"]} accent="emerald" />
        </div>
        <VerticalLink />
        <div className="flex justify-center"><span className="border border-border-pg bg-bg-panel-muted px-4 py-1 text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-text-pg-muted rounded-full">{copy.trader}</span></div>
        <VerticalLink />

        {/* Trader internals */}
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <FlowNode title={copy.portfolio} items={[]} />
          <FlowNode title={copy.dataEngine} items={[]} />
          <FlowNode title={copy.strategyQuoter} items={[]} />
          <FlowNode title={copy.strategyHedger} items={[]} />
          <FlowNode title={copy.execEngine} items={[]} />
          <FlowNode title={copy.riskEngine} items={[]} accent="emerald" />
        </div>

        <VerticalLink />
        <Bus>{copy.messageBus}</Bus>
        <VerticalLink />

        <div className="mx-auto max-w-md">
          <FlowNode title={copy.cache} items={[]} />
        </div>
        <VerticalLink />

        <div className="mx-auto max-w-md">
          <div className="border border-border-pg bg-bg-panel-muted p-3 text-center text-xs text-text-pg rounded-lg">{copy.database}</div>
        </div>
      </div>
    </div>
  );
}
