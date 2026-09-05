"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Search, ArrowUp, ArrowDown, CornerDownLeft, Command } from "lucide-react";

type CommandItem = {
  href: string;
  label: string;
  labelZh: string;
  hint: string;
  hintZh: string;
  keywords: string;
};

const COMMANDS: CommandItem[] = [
  { href: "/dashboard", label: "Dashboard", labelZh: "市场总览", hint: "Open intelligence briefing", hintZh: "打开智能市场简报", keywords: "dashboard home market briefing intelligence" },
  { href: "/chat", label: "Agent Chat", labelZh: "Agent 对话", hint: "Research with PureGamma Agent", hintZh: "与 PureGamma Agent 研究市场", keywords: "agent chat research ai assistant" },
  { href: "/portfolio", label: "Portfolio", labelZh: "投资组合", hint: "Positions, NAV and risk", hintZh: "持仓、净值与风险", keywords: "portfolio nav holdings positions risk" },
  { href: "/research", label: "Research", labelZh: "研究", hint: "Cross-asset research workspace", hintZh: "跨资产研究工作区", keywords: "research reports thesis evidence" },
  { href: "/reports", label: "Reports", labelZh: "报告", hint: "Open saved intelligence reports", hintZh: "打开已保存的研究报告", keywords: "reports archive intelligence" },
  { href: "/options", label: "Options", labelZh: "期权", hint: "Options and volatility intelligence", hintZh: "期权与波动率分析", keywords: "options volatility gamma derivatives" },
  { href: "/backtest", label: "Backtest", labelZh: "回测", hint: "Strategy backtesting workspace", hintZh: "策略回测工作区", keywords: "backtest strategy quant" },
  { href: "/gateway", label: "API Gateway", labelZh: "API 网关", hint: "Models, usage and routing", hintZh: "模型、用量与路由", keywords: "gateway api models usage routing" },
  { href: "/memory", label: "Memory", labelZh: "记忆", hint: "Manage persistent intelligence context", hintZh: "管理长期智能上下文", keywords: "memory context preferences" },
  { href: "/account", label: "Account", labelZh: "账户", hint: "Profile, security and preferences", hintZh: "个人资料、安全与偏好", keywords: "account profile settings security" },
];

function localeFromPath(pathname: string | null) {
  return pathname?.match(/^\/(zh|en)(?:\/|$)/)?.[1] === "zh" ? "zh" : "en";
}

function localizedHref(pathname: string | null, href: string) {
  const locale = localeFromPath(pathname);
  return pathname?.match(/^\/(zh|en)(?:\/|$)/) ? `/${locale}${href}` : href;
}

/**
 * Global interaction coordinator for the Apple Fluid layer.
 * - tracks keyboard vs pointer modality without touching business state
 * - exposes scroll-edge state for chrome/material changes
 * - adds a restrained route-enter continuity cue
 * - provides a keyboard-first Cmd/Ctrl+K navigation palette
 */
export function AppleContinuity() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollFrameRef = useRef<number | null>(null);
  const zh = localeFromPath(pathname) === "zh";

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return COMMANDS;
    return COMMANDS.filter((item) => `${item.label} ${item.labelZh} ${item.keywords}`.toLowerCase().includes(needle));
  }, [query]);

  useEffect(() => {
    const root = document.documentElement;
    const onPointer = () => { root.dataset.inputModality = "pointer"; };
    const onKeyboard = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      root.dataset.inputModality = "keyboard";
    };
    window.addEventListener("pointerdown", onPointer, true);
    window.addEventListener("keydown", onKeyboard, true);
    return () => {
      window.removeEventListener("pointerdown", onPointer, true);
      window.removeEventListener("keydown", onKeyboard, true);
    };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      scrollFrameRef.current = null;
      root.dataset.scrollEdge = window.scrollY > 12 ? "scrolled" : "top";
    };
    const onScroll = () => {
      if (scrollFrameRef.current === null) scrollFrameRef.current = window.requestAnimationFrame(apply);
    };
    apply();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (scrollFrameRef.current !== null) window.cancelAnimationFrame(scrollFrameRef.current);
    };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    root.dataset.routeMotion = "enter";
    const frame = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => { root.dataset.routeMotion = "settled"; });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pathname]);

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    setQuery("");
    setActiveIndex(0);
    const frame = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previous;
    };
  }, [open]);

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(matches.length - 1, 0)));
  }, [matches.length]);

  const navigate = (item: CommandItem) => {
    setOpen(false);
    router.push(localizedHref(pathname, item.href));
  };

  if (!open) return null;

  return (
    <div className="af-command-layer" role="presentation">
      <button className="af-command-backdrop" type="button" aria-label={zh ? "关闭命令面板" : "Close command palette"} onClick={() => setOpen(false)} />
      <section className="af-command-palette" role="dialog" aria-modal="true" aria-label={zh ? "快速导航" : "Quick navigation"}>
        <div className="af-command-search-row">
          <Search className="h-4 w-4" aria-hidden />
          <input
            ref={inputRef}
            className="af-command-input"
            value={query}
            onChange={(event) => { setQuery(event.target.value); setActiveIndex(0); }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActiveIndex((current) => matches.length ? (current + 1) % matches.length : 0);
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActiveIndex((current) => matches.length ? (current - 1 + matches.length) % matches.length : 0);
              } else if (event.key === "Enter" && matches[activeIndex]) {
                event.preventDefault();
                navigate(matches[activeIndex]);
              }
            }}
            placeholder={zh ? "前往页面或搜索工作区…" : "Go to a page or search the workspace…"}
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="af-command-kbd">Esc</kbd>
        </div>

        <div className="af-command-list" role="listbox" aria-label={zh ? "页面" : "Pages"}>
          {matches.length ? matches.map((item, index) => (
            <button
              key={item.href}
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              className={`af-command-item ${index === activeIndex ? "is-active" : ""}`}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => navigate(item)}
            >
              <span className="af-command-item-main">
                <span className="af-command-item-label">{zh ? item.labelZh : item.label}</span>
                <span className="af-command-item-hint">{zh ? item.hintZh : item.hint}</span>
              </span>
              {index === activeIndex ? <CornerDownLeft className="h-3.5 w-3.5" aria-hidden /> : null}
            </button>
          )) : (
            <div className="af-command-empty">{zh ? "没有匹配的页面" : "No matching pages"}</div>
          )}
        </div>

        <footer className="af-command-footer">
          <span><ArrowUp className="h-3 w-3" /><ArrowDown className="h-3 w-3" /> {zh ? "选择" : "select"}</span>
          <span><CornerDownLeft className="h-3 w-3" /> {zh ? "打开" : "open"}</span>
          <span><Command className="h-3 w-3" />K {zh ? "切换" : "toggle"}</span>
        </footer>
      </section>
    </div>
  );
}
