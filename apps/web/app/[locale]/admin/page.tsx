import type { Metadata } from "next";
import Link from "next/link";
import { AdminCreditConsole } from "@/components/admin-credit-console";
import { Badge, ErrorState, MetricCard, PageHeader, ResearchCard, StatusDot } from "@/components/puregamma";
import { getAdminLlmStatus, getAdminOverview, getAdminSystemStatus, getAdminUsers, getAdminWorkers } from "@/lib/api";
import { localizedMetadata } from "@/lib/metadata";
import { getMessageNamespace } from "@/lib/translations";
import { isLocale, type Locale, withLocale } from "@/i18n/routing";

function maskEmail(email: string) {
  const [local, domain = "masked"] = email.split("@");
  const maskedLocal = local.length <= 2 ? `${local[0] || "*"}***` : `${local.slice(0, 2)}***`;
  const domainParts = domain.split(".");
  const maskedDomain = domainParts.length > 1 ? `****.${domainParts.slice(1).join(".")}` : "****";
  return `${maskedLocal}@${maskedDomain}`;
}

export function generateMetadata({ params }: { params: { locale: string } }): Metadata {
  const locale = isLocale(params.locale) ? params.locale : "en";
  return localizedMetadata(locale, "admin", "/admin");
}

/** A read that failed must never be rendered as a healthy zero. */
function readState(source: { unavailable?: boolean; unauthorized?: boolean }) {
  if (source.unauthorized) return "unauthorized" as const;
  if (source.unavailable) return "unavailable" as const;
  return "ok" as const;
}

export default async function AdminPage({ params }: { params: { locale: Locale } }) {
  const locale = params.locale;
  const zh = locale === "zh";
  const copy = getMessageNamespace(locale, "admin");
  const [overview, system, workers, llmStatus, users] = await Promise.all([
    getAdminOverview(locale),
    getAdminSystemStatus(locale),
    getAdminWorkers(locale),
    getAdminLlmStatus(locale),
    getAdminUsers(locale),
  ]);

  const overviewState = readState(overview);
  const systemState = readState(system);
  const workersState = readState(workers);
  const counts = overview.counts;
  const unauthorized = [overviewState, systemState, workersState].includes("unauthorized");
  const degraded = !unauthorized && [overviewState, systemState, workersState].includes("unavailable");
  const failedReads = systemState === "unavailable" || workersState === "unavailable";

  // `?` means "not read"; `0` means the backend reported zero. They are not the
  // same claim, so they never share a rendering.
  const count = (value: number | undefined) => (overviewState === "ok" ? String(value ?? 0) : "—");
  const workerStatus = typeof workers.celery?.status === "string" ? workers.celery.status : null;
  const queueDepth = Object.values(workers.queues ?? {}).reduce((sum, value) => sum + (Number(value) || 0), 0);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={zh ? "用户、计费、投递与任务队列的只读审计视图。所有数值来自 Admin 接口。" : "A read-only audit view of users, billing, delivery and the worker queue. Every value comes from the Admin API."}
        sectionNumber="08"
      />

      {unauthorized ? <ErrorState title={copy.unauthorizedTitle} description={copy.unauthorizedDescription} /> : null}
      {degraded ? (
        <ResearchCard className="border-status-warning">
          <p className="text-sm text-status-warning">
            {zh
              ? "部分管理数据读取失败，下面对应位置以「—」或「读取失败」显示，未用 0 代替。"
              : "Some admin reads failed. The affected values below show “—” or “unavailable” rather than 0."}
          </p>
        </ResearchCard>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label={copy.modules.users} value={count(counts.users)} detail={copy.details.maskedAuditView} tone="info" />
        <MetricCard label={copy.modules.reports} value={count(counts.reports)} detail={copy.details.generatedResearch} tone="emerald" />
        <MetricCard
          label={zh ? "24 小时 LLM 调用" : "LLM calls, 24h"}
          value={count(counts.llm_calls_24h)}
          detail={zh ? "来自调用日志" : "From the call log"}
          tone="cyan"
        />
        <MetricCard
          label={zh ? "24 小时失败投递" : "Failed deliveries, 24h"}
          value={count(counts.deliveries_failed_24h)}
          detail={zh ? "通知投递失败数" : "Notification delivery failures"}
          tone={overviewState === "ok" && counts.deliveries_failed_24h > 0 ? "amber" : "neutral"}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <ResearchCard>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">{zh ? "运行状态" : "Runtime status"}</h2>
            <span className="text-xs text-text-pg-dim">
              {overviewState === "ok" && overview.generated_at ? `${zh ? "读取于" : "Read at"} ${new Date(overview.generated_at).toLocaleString(locale)}` : null}
            </span>
          </div>
          {systemState === "ok" ? (
            <dl className="mt-3 space-y-2 text-sm">
              {[
                { label: zh ? "数据库" : "Database", value: system.database || "—", ok: system.database === "ok" },
                { label: "Redis", value: system.redis === "not_checked" ? (zh ? "未检测" : "not checked") : system.redis || "—", ok: system.redis === "ok" },
                { label: zh ? "计费模式" : "Billing mode", value: `${system.billing_mode || "—"} / ${system.billing_checkout_mode || "—"}`, ok: system.billing_mode === "live" },
                { label: "Stripe", value: system.stripe_configured ? (zh ? "已配置" : "configured") : (zh ? "未配置" : "not configured"), ok: system.stripe_configured },
                { label: "iMessage", value: system.imessage_status || "—", ok: system.imessage_status === "macos_relay" || system.imessage_status === "photon" },
                { label: zh ? "真实计费" : "Live billing", value: system.mock_mode ? (zh ? "包含 mock 通道" : "includes mock") : (zh ? "全部真实" : "all live"), ok: !system.mock_mode },
              ].map((row) => (
                <div key={row.label} className="flex items-center justify-between gap-3 border-t border-border-pg pt-2 first:border-t-0 first:pt-0">
                  <dt className="text-text-pg-muted">{row.label}</dt>
                  <dd className="inline-flex items-center gap-2">
                    <StatusDot tone={row.ok ? "emerald" : "amber"} />
                    <span className="font-mono text-xs">{row.value}</span>
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-3 text-sm text-text-pg-muted">{zh ? "运行状态读取失败。" : "Runtime status unavailable."}</p>
          )}
        </ResearchCard>

        <ResearchCard>
          <h2 className="font-semibold">{zh ? "任务队列" : "Workers and queues"}</h2>
          {workersState === "ok" ? (
            <div className="mt-3 space-y-2 text-sm">
              <div className="flex items-center justify-between border-t border-border-pg pt-2 first:border-t-0 first:pt-0">
                <span className="text-text-pg-muted">Celery</span>
                <span className="inline-flex items-center gap-2">
                  <StatusDot tone={workerStatus === "ok" ? "emerald" : workerStatus ? "amber" : "neutral"} />
                  <span className="font-mono text-xs">{workerStatus || (zh ? "无数据" : "no data")}</span>
                </span>
              </div>
              <div className="flex items-center justify-between border-t border-border-pg pt-2">
                <span className="text-text-pg-muted">{zh ? "队列积压" : "Queue depth"}</span>
                <span className="font-mono text-xs">{queueDepth}</span>
              </div>
              {workers.recent_sync_failures.length ? (
                <div className="border-t border-border-pg pt-2">
                  <div className="text-xs text-text-pg-muted">{zh ? "最近同步失败" : "Recent sync failures"}</div>
                  <ul className="mt-2 space-y-1">
                    {workers.recent_sync_failures.slice(0, 5).map((failure) => (
                      <li key={failure.id} className="flex items-center justify-between gap-2 text-xs">
                        <span className="min-w-0 truncate font-mono">{failure.provider_id || failure.id}</span>
                        <span className="text-status-warning">{failure.status}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="border-t border-border-pg pt-2 text-xs text-text-pg-dim">{zh ? "无最近同步失败" : "No recent sync failures"}</p>
              )}
            </div>
          ) : (
            <p className="mt-3 text-sm text-text-pg-muted">{zh ? "任务队列读取失败。" : "Worker status unavailable."}</p>
          )}
        </ResearchCard>
      </div>

      <ResearchCard>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">{copy.modules.users}</h2>
          <span className="text-xs text-text-pg-dim">
            {users.unavailable ? (zh ? "读取失败" : "unavailable") : `${users.users.length}${typeof users.total === "number" ? ` / ${users.total}` : ""}`}
          </span>
        </div>
        {users.users.length ? (
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
                {users.users.slice(0, 25).map((user) => (
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
            {users.unavailable ? (zh ? "用户列表读取失败，未显示占位数据。" : "The user list could not be read; no placeholder data is shown.") : (zh ? "暂无用户。" : "No users yet.")}
          </p>
        )}
      </ResearchCard>

      <AdminCreditConsole locale={locale} />

      <ResearchCard className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">{zh ? "API Gateway 管理" : "API Gateway administration"}</h2>
          <p className="mt-1 text-sm text-text-pg-muted">
            {zh ? "Provider 健康、价格审批、用户限额与全站用量。" : "Provider health, price approvals, user limits, and platform usage."}
          </p>
        </div>
        <Link href={withLocale(locale, "/admin/gateway")} className="inline-flex min-h-10 items-center border border-border-pg-strong bg-pg-white px-3 py-2 text-sm font-semibold text-pg-black rounded-lg">
          {zh ? "打开管理台" : "Open console"}
        </Link>
      </ResearchCard>

      <ResearchCard>
        <h2 className="font-semibold">{zh ? "模型通道" : "Model lane"}</h2>
        {llmStatus.unavailable ? (
          <p className="mt-3 text-sm text-text-pg-muted">{zh ? "模型状态读取失败。" : "Model status unavailable."}</p>
        ) : (
          <div className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <div className="text-xs text-text-pg-muted">{zh ? "生效 Provider" : "Active provider"}</div>
              <div className="mt-1 font-mono text-xs">{llmStatus.active_provider || "—"}</div>
            </div>
            <div>
              <div className="text-xs text-text-pg-muted">{zh ? "模型" : "Model"}</div>
              <div className="mt-1 font-mono text-xs">{llmStatus.model || "—"}</div>
            </div>
            <div>
              <div className="text-xs text-text-pg-muted">{zh ? "状态" : "Status"}</div>
              <div className="mt-1 inline-flex items-center gap-2">
                <StatusDot tone={llmStatus.configured ? "emerald" : "amber"} />
                <span className="font-mono text-xs">{llmStatus.configured ? (zh ? "已配置" : "configured") : (zh ? "未配置" : "not configured")}</span>
              </div>
            </div>
          </div>
        )}
        {llmStatus.last_error ? <p className="mt-3 text-xs text-status-warning">{llmStatus.last_error}</p> : null}
      </ResearchCard>

      <p className="text-xs text-text-pg-dim">{copy.sensitiveNotice}</p>
    </div>
  );
}
