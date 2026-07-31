import Link from "next/link";

export type LegalSection = { title: string; body: React.ReactNode };

export function LegalPage({ eyebrow, title, updated, sections }: { eyebrow: string; title: string; updated: string; sections: LegalSection[] }) {
  return (
    <main className="legal shell">
      <nav className="nav">
        <Link className="brand" href="/"><span className="brandMark">PΓ</span><span>PUREGAMMA AI</span></Link>
        <Link className="textLink" href="/">返回首页 / Home</Link>
      </nav>
      <header className="legalHead">
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>最后更新 / Last updated: {updated}</p>
      </header>
      <div className="legalBody">
        {sections.map((section, index) => (
          <section key={section.title}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><h2>{section.title}</h2>{section.body}</div>
          </section>
        ))}
      </div>
      <footer className="footer"><p>© 2026 PureGamma AI</p><p>Research and decision support only.</p><a href="mailto:hello@puregamma.ai">hello@puregamma.ai</a></footer>
    </main>
  );
}
