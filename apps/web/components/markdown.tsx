"use client";

import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";

/** Every element override receives the same shape from react-markdown. */
type MdProps = { children?: ReactNode; className?: string; href?: string; src?: string; alt?: string };

/**
 * The product's single Markdown renderer.
 *
 * Before this, every assistant answer rendered through `prose prose-invert …`
 * classes that produced no CSS at all: `@tailwindcss/typography` is not a
 * dependency and `plugins: []` is empty, while `.pg-report` was referenced by
 * the class list and defined nowhere. `remark-gfm` was also absent, so pipe
 * tables were emitted as literal text. The practical effect was that headings
 * inherited body size, lists lost their markers to preflight, blockquotes and
 * tables had no styling, and code blocks had no language label and no copy
 * control — on the product's primary surface.
 *
 * Design notes:
 *  - Styling is applied through `components` overrides using the semantic
 *    `--pg-*` utilities rather than a typography plugin, so the type scale
 *    stays the one defined for this product instead of a library's defaults.
 *  - react-markdown v9 does not render raw HTML unless `rehype-raw` is added;
 *    it is deliberately NOT added, and it sanitizes URLs, so the existing
 *    safety boundary is preserved.
 *  - Code blocks get language label + copy, matching the interaction already
 *    used in the API docs and Gateway console.
 *  - Long content cannot escape its container: prose wraps, while `pre` and
 *    `table` scroll inside their own box.
 */

/** A fenced code block with a language label and a copy control. */
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="my-4 overflow-hidden border border-border-pg bg-bg-panel-muted rounded-lg">
      <div className="flex items-center justify-between gap-2 border-b border-border-pg px-3 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-pg-dim">{language || "text"}</span>
        <button
          type="button"
          onClick={() => void copy()}
          aria-label={copied ? "Copied" : "Copy code"}
          className="inline-flex min-h-7 items-center gap-1 px-1.5 text-[10px] text-text-pg-dim transition hover:text-text-pg rounded focus-visible:ring-2 focus-visible:ring-accent-ring focus-visible:outline-none"
        >
          {copied ? <Check className="h-3 w-3 text-status-positive" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="touch-pan-x overflow-x-auto overscroll-x-contain p-3 text-[13px] leading-[20px]">
        <code className="font-mono text-text-pg">{code}</code>
      </pre>
    </div>
  );
}

/**
 * Render a Markdown document.
 *
 * Element styling lives here rather than in a stylesheet so that the mapping is
 * visible next to the component tree; every value is a semantic token utility.
 */
export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="pg-markdown max-w-none break-words text-[14px] leading-[22px] text-text-pg">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }: MdProps) => <h1 className="mt-6 mb-3 text-[24px] font-medium leading-[32px] text-text-pg first:mt-0">{children}</h1>,
          h2: ({ children }: MdProps) => <h2 className="mt-6 mb-3 text-[20px] font-medium leading-[28px] text-text-pg first:mt-0">{children}</h2>,
          h3: ({ children }: MdProps) => <h3 className="mt-5 mb-2 text-[18px] font-medium leading-[26px] text-text-pg first:mt-0">{children}</h3>,
          h4: ({ children }: MdProps) => <h4 className="mt-4 mb-2 text-[16px] font-medium leading-[24px] text-text-pg first:mt-0">{children}</h4>,
          h5: ({ children }: MdProps) => <h5 className="mt-4 mb-1 text-[14px] font-medium leading-[22px] text-text-pg first:mt-0">{children}</h5>,
          h6: ({ children }: MdProps) => <h6 className="mt-4 mb-1 text-[13px] font-medium leading-[20px] text-text-pg-muted first:mt-0">{children}</h6>,

          p: ({ children }: MdProps) => <p className="my-4 leading-[22px] text-text-pg-muted first:mt-0 last:mb-0">{children}</p>,

          ul: ({ children }: MdProps) => <ul className="my-4 list-disc space-y-1.5 pl-6 text-text-pg-muted">{children}</ul>,
          ol: ({ children }: MdProps) => <ol className="my-4 list-decimal space-y-1.5 pl-6 text-text-pg-muted">{children}</ol>,
          li: ({ children }: MdProps) => <li className="leading-[22px] [&>p]:my-0">{children}</li>,

          blockquote: ({ children }: MdProps) => (
            <blockquote className="my-4 border-l-2 border-border-pg-strong pl-4 text-text-pg-muted italic">{children}</blockquote>
          ),

          hr: () => <hr className="my-6 border-0 border-t border-border-pg" />,

          a: ({ href, children }: MdProps) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent underline decoration-transparent underline-offset-2 transition hover:decoration-current"
            >
              {children}
            </a>
          ),

          strong: ({ children }: MdProps) => <strong className="font-medium text-text-pg">{children}</strong>,
          em: ({ children }: MdProps) => <em className="italic">{children}</em>,
          del: ({ children }: MdProps) => <del className="text-text-pg-dim line-through">{children}</del>,

          // Block code arrives as <pre><code class="language-x">. Inline code is
          // a bare <code> with no newline, so the two are told apart by whether
          // the content contains a line break.
          pre: ({ children }: MdProps) => <>{children}</>,
          code: ({ className, children }: MdProps) => {
            const text = String(children ?? "");
            const isBlock = text.includes("\n") || Boolean(className);
            if (!isBlock) {
              return <code className="border border-border-pg bg-bg-panel-muted px-1.5 py-0.5 font-mono text-[13px] text-text-pg rounded">{children}</code>;
            }
            const language = /language-([\w+-]+)/.exec(className || "")?.[1] ?? "";
            return <CodeBlock language={language} code={text.replace(/\n$/, "")} />;
          },

          // Tables scroll inside their own container; they are never allowed to
          // widen the page, and the wrapper is what receives the overflow.
          table: ({ children }: MdProps) => (
            <div className="my-4 touch-pan-x overflow-x-auto overscroll-x-contain border border-border-pg rounded-lg">
              <table className="w-full border-collapse text-[13px] leading-[20px]">{children}</table>
            </div>
          ),
          thead: ({ children }: MdProps) => <thead className="bg-bg-panel-muted text-text-pg-secondary">{children}</thead>,
          th: ({ children }: MdProps) => <th className="border-b border-border-pg px-3 py-2 text-left font-medium">{children}</th>,
          td: ({ children }: MdProps) => <td className="border-b border-border-pg px-3 py-2 text-text-pg-muted last:border-b-0">{children}</td>,
          tr: ({ children }: MdProps) => <tr className="last:[&>td]:border-b-0">{children}</tr>,

          img: ({ src, alt }: MdProps) => <img src={typeof src === "string" ? src : undefined} alt={alt ?? ""} className="my-4 max-w-full rounded-lg" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/** Back-compat alias for the previous 7-line re-export. */
export function Markdown({ content }: { content: string }) {
  return <MarkdownContent content={content} />;
}
