import Link from "next/link";
import Image from "next/image";
import type { ReactNode } from "react";

export type PublicLegalSection = {
  title: string;
  body: ReactNode;
};

export function PublicLegalPage({
  eyebrow,
  title,
  updated,
  sections,
}: {
  eyebrow: string;
  title: string;
  updated: string;
  sections: PublicLegalSection[];
}) {
  return (
    <main className="relative z-10 mx-auto min-h-screen w-full max-w-5xl px-5 py-8 sm:px-8 lg:px-10">
      <nav className="flex items-center justify-between border-b border-border-pg pb-5">
        <Link href="/" className="inline-flex items-center gap-2 text-sm font-semibold tracking-wide">
          <Image src="/logo.png" alt="PureGamma AI" width={28} height={28} />
          PUREGAMMA AI
        </Link>
        <Link href="/" className="text-xs text-text-pg-muted underline underline-offset-4 hover:text-text-pg">
          返回首页 / Home
        </Link>
      </nav>

      <header className="border-b border-border-pg py-14 sm:py-20">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-text-pg-muted">{eyebrow}</p>
        <h1 className="mt-5 whitespace-pre-line text-4xl font-semibold leading-tight sm:text-6xl">{title}</h1>
        <p className="mt-5 text-xs text-text-pg-muted">最后更新 / Last updated: {updated}</p>
      </header>

      <div className="pb-20 pt-4">
        {sections.map((section, index) => (
          <section key={section.title} className="grid gap-4 border-b border-border-pg py-9 sm:grid-cols-[64px_minmax(0,760px)] sm:gap-7">
            <span className="text-xs text-text-pg-dim">{String(index + 1).padStart(2, "0")}</span>
            <div className="space-y-3 text-sm leading-7 text-text-pg-muted [&_a]:text-text-pg [&_a]:underline [&_a]:underline-offset-4 [&_h2]:mb-4 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-text-pg [&_p]:m-0">
              <h2>{section.title}</h2>
              {section.body}
            </div>
          </section>
        ))}
      </div>

      <footer className="flex flex-col gap-3 border-t border-border-pg py-8 text-xs text-text-pg-dim sm:flex-row sm:items-center sm:justify-between">
        <span>© 2026 PureGamma AI</span>
        <span>Research and decision support only.</span>
        <a className="underline underline-offset-4" href="mailto:hello@puregamma.ai">hello@puregamma.ai</a>
      </footer>
    </main>
  );
}
