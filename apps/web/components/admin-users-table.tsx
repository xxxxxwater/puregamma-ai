"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2, Search } from "lucide-react";
import { Badge, ResearchCard } from "@/components/puregamma";
import { getAdminUsers, type AdminUserRow } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

/**
 * Admin user table.
 *
 * Every control is a server query: `q`, `role` and `plan` go to
 * `GET /admin/users`, which filters in SQL and returns `total` counted from the
 * same filtered query. Filtering the rows already on screen would answer a
 * search with one page of a larger result set while looking like a full result,
 * which is the failure mode this table exists to avoid.
 */

const PAGE_SIZE = 25;
const ROLES = ["admin", "user"] as const;
const PLANS = ["Free", "Pro", "Max", "Enterprise"] as const;

function maskEmail(email: string) {
  const [local, domain = "masked"] = (email || "").split("@");
  const maskedLocal = local.length <= 2 ? `${local[0] || "*"}***` : `${local.slice(0, 2)}***`;
  const domainParts = domain.split(".");
  const maskedDomain = domainParts.length > 1 ? `****.${domainParts.slice(1).join(".")}` : "****";
  return `${maskedLocal}@${maskedDomain}`;
}

type State = {
  rows: AdminUserRow[];
  total: number | null;
  hasMore: boolean;
  loading: boolean;
  /** null = not read yet; a string = the read failed and the UI must say so. */
  error: string | null;
};

export function AdminUsersTable({ locale, initial }: { locale: Locale; initial: { rows: AdminUserRow[]; total: number | null; hasMore: boolean; failed: boolean } }) {
  const zh = locale === "zh";
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [plan, setPlan] = useState("");
  const [offset, setOffset] = useState(0);
  const [state, setState] = useState<State>(() => ({
    rows: initial.rows,
    total: initial.total,
    hasMore: initial.hasMore,
    loading: false,
    error: initial.failed ? (zh ? "用户列表读取失败。" : "User list unavailable.") : null,
  }));
  /** Guards against an older response overwriting a newer one. */
  const requestRef = useRef(0);

  const filters = useMemo(() => ({ q: query.trim(), role, plan }), [query, role, plan]);

  const load = async (nextOffset: number) => {
    const token = ++requestRef.current;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const result = await getAdminUsers(locale, { ...filters, limit: PAGE_SIZE, offset: nextOffset });
      if (token !== requestRef.current) return;
      const rows = Array.isArray(result.users) ? result.users : [];
      setState({
        rows,
        total: typeof result.total === "number" ? result.total : null,
        hasMore: Boolean(result.has_more),
        loading: false,
        error: result.unavailable ? (zh ? "用户列表读取失败。" : "User list unavailable.") : null,
      });
      setOffset(nextOffset);
    } catch {
      if (token !== requestRef.current) return;
      setState((current) => ({
        ...current,
        rows: [],
        total: null,
        hasMore: false,
        loading: false,
        error: zh ? "用户列表读取失败，未显示占位数据。" : "The user list could not be read; no placeholder data is shown.",
      }));
    }
  };

  // Debounce the free-text box; a click on a select reloads immediately.
  useEffect(() => {
    const first = offset === 0;
    const timer = window.setTimeout(() => { void load(0); }, first ? 0 : 250);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.q, filters.role, filters.plan]);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = state.total != null ? Math.max(1, Math.ceil(state.total / PAGE_SIZE)) : null;
  const filtered = Boolean(filters.q || filters.role || filters.plan);

  return (
    <ResearchCard>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">{zh ? "用户" : "Users"}</h2>
        <span className="text-xs text-text-pg-dim" data-testid="admin-users-count">
          {state.error
            ? (zh ? "读取失败" : "unavailable")
            : state.total == null
              ? `${state.rows.length}`
              : `${state.total}${filtered ? (zh ? " 条匹配" : " matching") : ""}`}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-xs text-text-pg-muted">
          <span className="mb-1 block">{zh ? "搜索邮箱或姓名" : "Search email or name"}</span>
          <span className="relative block">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-pg-dim" aria-hidden />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={zh ? "例如 alice@example.com" : "e.g. alice@example.com"}
              className="min-h-9 w-56 border border-border-pg bg-bg-panel pl-7 pr-2 text-sm outline-none focus:border-border-pg-strong rounded-lg"
            />
          </span>
        </label>
        <label className="text-xs text-text-pg-muted">
          <span className="mb-1 block">{zh ? "角色" : "Role"}</span>
          <select value={role} onChange={(event) => setRole(event.target.value)} className="min-h-9 border border-border-pg bg-bg-panel px-2 text-sm outline-none focus:border-border-pg-strong rounded-lg">
            <option value="">{zh ? "全部" : "All"}</option>
            {ROLES.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="text-xs text-text-pg-muted">
          <span className="mb-1 block">{zh ? "套餐" : "Plan"}</span>
          <select value={plan} onChange={(event) => setPlan(event.target.value)} className="min-h-9 border border-border-pg bg-bg-panel px-2 text-sm outline-none focus:border-border-pg-strong rounded-lg">
            <option value="">{zh ? "全部" : "All"}</option>
            {PLANS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        {filtered ? (
          <button type="button" onClick={() => { setQuery(""); setRole(""); setPlan(""); }} className="min-h-9 border border-border-pg px-3 text-xs text-text-pg-muted transition hover:border-border-pg-strong hover:text-text-pg rounded-lg">
            {zh ? "清除筛选" : "Clear filters"}
          </button>
        ) : null}
      </div>

      {state.error ? (
        <p className="mt-3 text-sm text-status-warning" data-testid="admin-users-error">{state.error}</p>
      ) : state.rows.length ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.1em] text-text-pg-muted">
              <tr>
                <th className="pb-2 font-medium">{zh ? "账号" : "Account"}</th>
                <th className="pb-2 font-medium">{zh ? "角色" : "Role"}</th>
                <th className="pb-2 font-medium">{zh ? "套餐" : "Plan"}</th>
                <th className="pb-2 font-medium">{zh ? "等级" : "Tier"}</th>
              </tr>
            </thead>
            <tbody>
              {state.rows.map((user) => (
                <tr key={user.id} className="border-t border-border-pg">
                  <td className="py-2 font-mono text-xs">{maskEmail(user.email)}</td>
                  <td className="py-2"><Badge tone={user.role === "admin" ? "amber" : "neutral"}>{user.role}</Badge></td>
                  <td className="py-2 text-text-pg-muted">{user.plan || "—"}</td>
                  <td className="py-2 text-text-pg-muted">{user.membership_tier || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-text-pg-muted">
          {filtered ? (zh ? "没有匹配的账号。" : "No accounts match.") : (zh ? "暂无用户。" : "No users yet.")}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border-pg pt-3 text-xs text-text-pg-muted">
        <span className="inline-flex items-center gap-2">
          {state.loading ? <><Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />{zh ? "加载中…" : "Loading…"}</> : null}
          {totalPages != null ? (zh ? `第 ${page} / ${totalPages} 页` : `Page ${page} of ${totalPages}`) : null}
        </span>
        <span className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0 || state.loading}
            onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}
            className="inline-flex min-h-9 items-center gap-1 border border-border-pg px-2.5 transition hover:border-border-pg-strong disabled:opacity-40 rounded-lg"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden />{zh ? "上一页" : "Previous"}
          </button>
          <button
            type="button"
            disabled={!state.hasMore || state.loading}
            onClick={() => void load(offset + PAGE_SIZE)}
            className="inline-flex min-h-9 items-center gap-1 border border-border-pg px-2.5 transition hover:border-border-pg-strong disabled:opacity-40 rounded-lg"
          >
            {zh ? "下一页" : "Next"}<ChevronRight className="h-3.5 w-3.5" aria-hidden />
          </button>
        </span>
      </div>
    </ResearchCard>
  );
}
