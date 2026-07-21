"use client";

import { FormEvent, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Loader2, LockKeyhole } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { Button } from "@/components/ui";
import { internalAdminLogin } from "@/lib/api";
import { withLocale } from "@/i18n/routing";

const inputClass = "min-h-11 w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg outline-none focus:border-border-pg-strong";

export default function InternalAdminLoginPage() {
  const locale = useLocale();
  const router = useRouter();
  const zh = locale === "zh";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await internalAdminLogin(username, password);
      if (result.user.role !== "admin") throw new Error("Administrator role required");
      localStorage.setItem("pg_user", JSON.stringify(result.user));
      router.replace(withLocale(locale, "/admin"));
      router.refresh();
    } catch {
      setError(zh ? "管理员用户名或密码无效，或内部登录尚未启用。" : "Invalid administrator credentials or internal login is disabled.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <div className="w-full max-w-sm border border-border-pg bg-bg-panel p-6">
        <div className="mb-6 text-center">
          <Image src="/logo.png" alt="PureGamma" width={36} height={36} className="mx-auto" />
          <h1 className="mt-4 text-xl font-semibold">PureGamma Internal</h1>
          <p className="mt-2 text-xs text-text-pg-muted">{zh ? "仅限授权内部人员" : "Authorized personnel only"}</p>
        </div>
        {error ? <p className="mb-4 border border-status-negative/40 p-3 text-sm text-status-negative">{error}</p> : null}
        <form className="space-y-4" onSubmit={submit}>
          <label className="block text-xs text-text-pg-muted">{zh ? "管理员用户名" : "Administrator username"}<input className={`${inputClass} mt-1`} autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
          <label className="block text-xs text-text-pg-muted">{zh ? "密码" : "Password"}<input className={`${inputClass} mt-1`} type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          <Button className="w-full" type="submit" disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LockKeyhole className="h-4 w-4" />}{zh ? "进入管理后台" : "Enter administration"}</Button>
        </form>
      </div>
    </div>
  );
}

