import Link from "next/link";

/** Shown inside the app shell when a localized page calls notFound(). */
export default function LocaleNotFound() {
  return (
    <section className="mx-auto mt-6 max-w-xl rounded-2xl border border-border-pg bg-bg-panel p-6" data-testid="route-not-found">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-text-pg-muted">404</p>
      <h1 className="mt-3 text-xl font-semibold">Page not found · 页面不存在</h1>
      <p className="mt-2 text-sm leading-6 text-text-pg-muted">The address may be out of date. · 链接可能已失效。</p>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link href="/en/dashboard" className="inline-flex min-h-10 items-center rounded-lg border border-border-pg px-4 text-sm hover:border-border-pg-strong">Workspace</Link>
        <Link href="/zh/dashboard" className="inline-flex min-h-10 items-center rounded-lg border border-border-pg px-4 text-sm hover:border-border-pg-strong">工作台</Link>
      </div>
    </section>
  );
}
