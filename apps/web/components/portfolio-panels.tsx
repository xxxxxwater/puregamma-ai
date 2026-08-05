import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { ResearchCard } from "@/components/puregamma";
import type { PortfolioHolding } from "@/lib/api";

export function HoldingRow({ holding, zh, money, pct, quantity }: { holding: PortfolioHolding; zh: boolean; money: (value: number) => string; pct: (value: number | null | undefined) => string; quantity: (value: number) => string }) {
  const change = holding.change_24h_pct || (holding.value > 0 && holding.change_24h !== 0 ? (holding.change_24h / Math.max(holding.value - holding.change_24h, 1e-9)) * 100 : 0);
  return <tr>
    <td className="px-4 py-3"><div className="flex items-center gap-2"><span className="font-medium">{holding.symbol}</span>{holding.native ? <span className="border border-border-pg px-1 py-0.5 text-[9px] text-text-pg-dim">NATIVE</span> : null}{!holding.verified ? <span className="border border-status-warning px-1 py-0.5 text-[9px] text-status-warning">{zh ? "未验证" : "UNVERIFIED"}</span> : null}{!holding.priced ? <span className="border border-border-pg px-1 py-0.5 text-[9px] text-text-pg-dim">{zh ? "无报价" : "NO PRICE"}</span> : null}</div><div className="mt-0.5 max-w-40 truncate text-[10px] text-text-pg-dim">{holding.name}</div></td>
    <td className="px-3 py-3">{holding.chain ? <span className="border border-border-pg px-1.5 py-0.5 font-mono text-[10px] uppercase text-text-pg-muted">{holding.chain}</span> : <span className="text-text-pg-dim">--</span>}</td>
    <td className="px-3 py-3 text-right font-mono">{quantity(holding.quantity)}</td>
    <td className="px-3 py-3 text-right font-mono">{holding.priced ? money(holding.price) : "--"}</td>
    <td className={`px-3 py-3 text-right font-mono ${change > 0 ? "text-status-positive" : change < 0 ? "text-status-negative" : "text-text-pg-dim"}`}>{holding.priced ? pct(change) : "--"}</td>
    <td className="px-3 py-3 text-right font-medium">{money(holding.value)}</td>
    <td className="px-4 py-3"><div className="flex items-center justify-end gap-2"><div className="h-1 w-16 bg-bg-panel-muted"><div className="h-1 bg-text-pg" style={{ width: `${Math.min(Math.max(holding.weight * 100, 2), 100)}%` }} /></div><span className="font-mono text-[10px] text-text-pg-muted">{(holding.weight * 100).toFixed(1)}%</span></div></td>
  </tr>;
}

export function ProviderCard({ icon, name, status, description, action, busy, onClick, disabled }: { icon: ReactNode; name: string; status?: string; description: string; action: string; busy: boolean; onClick: () => void; disabled: boolean }) { return <ResearchCard><div className="flex items-start justify-between">{icon}{status ? <span className="text-[10px] text-status-warning">{status}</span> : null}</div><h3 className="mt-4 font-semibold">{name}</h3><p className="mt-2 min-h-10 text-xs leading-5 text-text-pg-muted">{description}</p><button type="button" disabled={disabled || busy} onClick={onClick} className="mt-4 h-10 w-full border border-border-pg-strong text-xs font-medium disabled:opacity-40">{busy ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : action}</button></ResearchCard>; }

export function AutopilotToggle({ label, detail, value, onChange }: { label: string; detail: string; value: boolean; onChange: (value: boolean) => void }) { return <div className="flex items-center gap-3 bg-bg-panel p-4"><div className="min-w-0 flex-1"><div className="text-xs font-medium">{label}</div><div className="mt-1 text-[10px] text-text-pg-dim">{detail}</div></div><input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} className="h-4 w-4 accent-[var(--foreground)]" /></div>; }
