"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BadgeCheck, Chrome, Key, Loader2, LogOut, MessageCircle, UserRound } from "lucide-react";
import { PageHeader, ResearchCard } from "@/components/puregamma";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { withLocale } from "@/i18n/routing";
import { AuthResponse, changePassword, getAgentQuota, getMe, logout, requestIMessageVerification, setPassword } from "@/lib/api";
import { t } from "@/lib/translations";

export default function AccountPage() {
  const locale = useLocale();
  const zh = locale === "zh";
  const router = useRouter();
  const [user, setUser] = useState<AuthResponse["user"] | null>(null);
  const [quota, setQuota] = useState<{ used: number; limit: number | null; remaining: number | null; credit_balance: number } | null>(null);
  const [error, setError] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [imessageAddress, setIMessageAddress] = useState("");
  const [bindingStatus, setBindingStatus] = useState("");
  useEffect(() => { Promise.all([getMe(), getAgentQuota()]).then(([me, usage]) => { setUser(me.user); setQuota(usage); }).catch((reason) => setError(String(reason))); }, []);
  const signOut = async () => { await logout(); localStorage.removeItem("pg_user"); router.replace(withLocale(locale, "/login")); };
  const requestBinding = async () => { setBindingStatus(""); try { const result = await requestIMessageVerification(imessageAddress); setIMessageAddress(result.recipient); setBindingStatus(zh ? "iMessage 已绑定。请用该地址向 PureGamma AI 发消息。" : "iMessage is bound. Message PureGamma AI from this address."); } catch (reason) { setBindingStatus(String(reason)); } };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPw || !newPw || newPw.length < 8) return;
    setPwBusy(true); setPwMsg("");
    try {
      const r = await changePassword(currentPw, newPw);
      setUser(r.user);
      setCurrentPw(""); setNewPw("");
      setPwMsg(t(locale, "common.auth.passwordChanged"));
    } catch { setPwMsg(zh ? "当前密码错误" : "Current password is incorrect"); }
    finally { setPwBusy(false); }
  };

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPw || newPw.length < 8) return;
    setPwBusy(true); setPwMsg("");
    try {
      const r = await setPassword(newPw);
      setUser(r.user);
      setNewPw("");
      setPwMsg(t(locale, "common.auth.passwordSet"));
    } catch { setPwMsg(zh ? "设置失败" : "Failed to set password"); }
    finally { setPwBusy(false); }
  };

  return <div className="space-y-5">
    <PageHeader eyebrow={zh ? "账户" : "Account"} title={zh ? "身份与用量" : "Identity and usage"} description={zh ? "查看登录身份、套餐和 Agent 用量。" : "Review sign-in identity, plan, and Agent usage."} sectionNumber="09" />
    {error ? <div className="border border-status-negative p-4 text-sm text-status-negative">{error}</div> : null}
    {user ? <div className="grid gap-4 lg:grid-cols-2">
      <ResearchCard><div className="flex items-start gap-4">{user.avatar_url ? <span aria-label={user.name} className="h-14 w-14 shrink-0 rounded-full border border-border-pg bg-cover bg-center" style={{ backgroundImage: `url(${user.avatar_url})` }} /> : <div className="grid h-14 w-14 place-items-center rounded-full border border-border-pg"><UserRound className="h-6 w-6" /></div>}<div className="min-w-0"><h2 className="truncate text-lg font-semibold">{user.name}</h2><p className="truncate text-sm text-text-pg-muted">{user.email}</p><div className="mt-3 flex flex-wrap gap-2">{user.login_methods?.map((method) => <span key={method} className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs">{method === "google" ? <Chrome className="h-3 w-3" /> : null}{method === "email" ? <Key className="h-3 w-3" /> : null}{method}</span>)}{user.email_verified ? <span className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs text-status-positive"><BadgeCheck className="h-3 w-3" />{zh ? "邮箱已验证" : "Email verified"}</span> : null}{user.has_password ? <span className="inline-flex items-center gap-1 border border-border-pg px-2 py-1 text-xs"><Key className="h-3 w-3" />{zh ? "已设密码" : "Password set"}</span> : null}</div></div></div><dl className="mt-5 grid grid-cols-2 gap-px border border-border-pg bg-border-pg text-sm"><div className="bg-bg-panel p-3"><dt className="text-text-pg-muted">{zh ? "最近登录" : "Last login"}</dt><dd className="mt-1">{user.last_login_at ? new Date(user.last_login_at).toLocaleString(locale) : "-"}</dd></div><div className="bg-bg-panel p-3"><dt className="text-text-pg-muted">{zh ? "当前套餐" : "Current plan"}</dt><dd className="mt-1 font-semibold">{user.plan}</dd></div></dl></ResearchCard>
      <ResearchCard><h2 className="font-semibold">Agent</h2><div className="mt-4 grid grid-cols-3 gap-px border border-border-pg bg-border-pg text-center"><div className="bg-bg-panel p-3"><div className="text-xs text-text-pg-muted">{zh ? "已用" : "Used"}</div><div className="mt-1 text-xl font-semibold">{quota?.used ?? 0}</div></div><div className="bg-bg-panel p-3"><div className="text-xs text-text-pg-muted">{zh ? "剩余" : "Remaining"}</div><div className="mt-1 text-xl font-semibold">{quota?.remaining ?? 0}</div></div><div className="bg-bg-panel p-3"><div className="text-xs text-text-pg-muted">Credits</div><div className="mt-1 text-xl font-semibold">{quota?.credit_balance ?? user.credit_balance}</div></div></div><button type="button" onClick={signOut} className="mt-5 inline-flex items-center gap-2 border border-border-pg px-3 py-2 text-sm hover:border-border-pg-strong"><LogOut className="h-4 w-4" />{zh ? "退出登录" : "Sign out"}</button></ResearchCard>
    </div> : null}

    {user ? <ResearchCard><h2 className="font-semibold">{user.has_password ? t(locale, "common.auth.changePasswordTitle") : t(locale, "common.auth.setPasswordTitle")}</h2><p className="mt-1 text-sm text-text-pg-muted">{user.has_password ? (zh ? "输入当前密码和新密码以修改。" : "Enter your current password and a new password to change.") : t(locale, "common.auth.setPasswordDescription")}</p><form onSubmit={user.has_password ? handleChangePassword : handleSetPassword} className="mt-4 space-y-3 max-w-sm">
      {user.has_password ? <input type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} placeholder={t(locale, "common.auth.currentPassword")} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong" required /> : null}
      <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder={t(locale, "common.auth.newPassword")} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong" required minLength={8} />
      <button type="submit" disabled={pwBusy} className="inline-flex items-center gap-2 border border-border-pg bg-text-pg px-4 py-2 text-sm font-semibold text-bg-panel transition hover:opacity-90 disabled:opacity-50">{pwBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}{user.has_password ? t(locale, "common.auth.changePasswordBtn") : t(locale, "common.auth.setPasswordBtn")}</button>
    </form>{pwMsg ? <p className="mt-3 text-sm text-text-pg-muted">{pwMsg}</p> : null}</ResearchCard> : null}

    <ResearchCard id="imessage-bind"><div className="flex items-start gap-3"><MessageCircle className="mt-0.5 h-5 w-5" /><div><h2 className="font-semibold">{zh ? "绑定 iMessage Agent" : "Bind iMessage Agent"}</h2><p className="mt-1 text-sm text-text-pg-muted">{zh ? "填写 iMessage 手机号（E.164 格式）或 Apple ID 邮箱即可绑定，不发送验证码。只有该地址向 PureGamma AI 发消息时才会进入你的 Agent 和记忆；其他地址不回复。" : "Bind an iMessage phone number (E.164) or Apple ID email. No code is sent. Only messages from this address enter your Agent memory; other senders receive no reply."}</p></div></div><div className="mt-4 flex gap-3"><input className="control flex-1" value={imessageAddress} onChange={(event) => setIMessageAddress(event.target.value)} placeholder="+12135550123 or name@icloud.com" /><button type="button" onClick={requestBinding} className="border border-border-pg px-3 py-2 text-sm">{zh ? "绑定" : "Bind"}</button></div>{bindingStatus ? <p className="mt-3 text-sm text-text-pg-muted">{bindingStatus}</p> : null}</ResearchCard>
  </div>;
}
