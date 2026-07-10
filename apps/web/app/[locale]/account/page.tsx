"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BadgeCheck, Chrome, LogOut, UserRound } from "lucide-react";
import { PageHeader, ResearchCard } from "@/components/puregamma";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { withLocale } from "@/i18n/routing";
import { AuthResponse, getAgentQuota, getMe, logout } from "@/lib/api";

export default function AccountPage() {
  const locale = useLocale();
  const zh = locale === "zh";
  const router = useRouter();
  const [user, setUser] = useState<AuthResponse["user"] | null>(null);
  const [quota, setQuota] = useState<{ used: number; limit: number; remaining: number; credit_balance: number } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([getMe(), getAgentQuota()]).then(([me, usage]) => { setUser(me.user); setQuota(usage); }).catch((reason) => setError(String(reason))); }, []);
  const signOut = async () => { await logout(); localStorage.removeItem("pg_user"); router.replace(withLocale(locale, "/login")); };
  return <div className="space-y-5">
    <PageHeader eyebrow={zh ? "账户" : "Account"} title={zh ? "身份与用量" : "Identity and usage"} description={zh ? "查看登录身份、套餐和 Agent 用量。" : "Review sign-in identity, plan, and Agent usage."} sectionNumber="09" />
    {error ? <div className="border border-status-negative p-4 text-sm text-status-negative">{error}</div> : null}
    {user ? <div className="grid gap-4 lg:grid-cols-2">
      <ResearchCard><div className="flex items-start gap-4">{user.avatar_url ? <span aria-label={user.name} className="h-14 w-14 shrink-0 rounded-full border border-border-pg bg-cover bg-center" style={{ backgroundImage: `url(${user.avatar_url})` }} /> : <div className="grid h-14 w-14 place-items-center rounded-full border border-border-pg"><UserRound className="h-6 w-6" /></div>}<div className="min-w-0"><h2 className="truncate text-lg font-semibold">{user.name}</h2><p className="truncate text-sm text-text-pg-muted">{user.email}</p><div className="mt-3 flex flex-wrap gap-2">{user.login_methods?.map((method) => <span key={method} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs">{method === "google" ? <Chrome className="h-3 w-3" /> : null}{method}</span>)}{user.email_verified ? <span className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs text-status-positive"><BadgeCheck className="h-3 w-3" />{zh ? "邮箱已验证" : "Email verified"}</span> : null}</div></div></div><dl className="mt-5 grid grid-cols-2 gap-px border border-border-pg bg-border-pg text-sm"><div className="bg-bg-panel p-3"><dt className="text-text-pg-muted">{zh ? "最近登录" : "Last login"}</dt><dd className="mt-1">{user.last_login_at ? new Date(user.last_login_at).toLocaleString(locale) : "-"}</dd></div><div className="bg-bg-panel p-3"><dt className="text-text-pg-muted">{zh ? "当前套餐" : "Current plan"}</dt><dd className="mt-1 font-semibold">{user.plan}</dd></div></dl></ResearchCard>
      <ResearchCard><h2 className="font-semibold">Agent</h2><div className="mt-4 grid grid-cols-3 gap-px border border-border-pg bg-border-pg text-center"><div className="bg-bg-panel p-3"><div className="text-xs text-text-pg-muted">{zh ? "已用" : "Used"}</div><div className="mt-1 text-xl font-semibold">{quota?.used ?? 0}</div></div><div className="bg-bg-panel p-3"><div className="text-xs text-text-pg-muted">{zh ? "剩余" : "Remaining"}</div><div className="mt-1 text-xl font-semibold">{quota?.remaining ?? 0}</div></div><div className="bg-bg-panel p-3"><div className="text-xs text-text-pg-muted">Credits</div><div className="mt-1 text-xl font-semibold">{quota?.credit_balance ?? user.credit_balance}</div></div></div><button type="button" onClick={signOut} className="mt-5 inline-flex items-center gap-2 border border-border-pg px-3 py-2 text-sm hover:border-border-pg-strong"><LogOut className="h-4 w-4" />{zh ? "退出登录" : "Sign out"}</button></ResearchCard>
    </div> : null}
  </div>;
}
