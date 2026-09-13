"use client";

import { Minus, Monitor, Moon, Plus, Sparkles, Sun } from "lucide-react";
import { applyVisualStyle, readVisualStyle, type VisualStyle } from "@/lib/visual-style";
import { SCALES, THEME_CYCLE, useAppearance, type FontScale, type ThemePreference } from "@/lib/appearance";
import { useEffect, useState } from "react";

function clsxLike(visualStyle: VisualStyle, base: string): string {
  // The glass style is the default: highlight the control only when the
  // user switched away, keeping the same visual language as other toggles.
  return visualStyle === "classic" ? `${base} border-border-pg-strong` : base;
}

/**
 * Theme / appearance controls.
 *
 * Mounted three times (sidebar rail, desktop top bar, mobile top bar). All
 * instances now read one shared store, so they cannot disagree, and the
 * preference survives a reload because the pre-paint script applies it before
 * first paint. The control is a three-state cycle — System → Light → Dark —
 * because a two-state switch cannot express "follow the OS", which was the
 * only way to get a first-load theme that matches the user's desktop.
 */
export function AppearanceControls({
  locale,
  showFontScale = true,
}: {
  locale: "en" | "zh";
  showFontScale?: boolean;
}) {
  const { preference, resolved, fontScale, setPreference, setFontScale } = useAppearance();
  const [visualStyle, setVisualStyle] = useState<VisualStyle>("glass");

  useEffect(() => { setVisualStyle(readVisualStyle()); }, []);

  const cycleTheme = () => {
    // "system" resolves to the OS preference, so the visible icon must reflect
    // the resolved theme, not merely the stored preference.
    const currentIndex = THEME_CYCLE.indexOf(preference);
    setPreference(THEME_CYCLE[(currentIndex + 1) % THEME_CYCLE.length]);
  };

  const applyStyle = (value: VisualStyle) => {
    setVisualStyle(value);
    applyVisualStyle(value);
  };

  const scaleIndex = SCALES.indexOf(fontScale);
  const buttonClass = "grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong disabled:opacity-35";

  const themeTitle =
    preference === "system"
      ? locale === "zh"
        ? `跟随系统（当前${resolved === "dark" ? "深色" : "浅色"}）· 点击切换`
        : `Following system (currently ${resolved}) · click to change`
      : locale === "zh"
        ? `主题：${preference === "dark" ? "深色" : "浅色"} · 点击切换`
        : `Theme: ${preference} · click to change`;

  const ThemeIcon = preference === "system" ? Monitor : resolved === "dark" ? Moon : Sun;

  return (
    <div className="flex items-center gap-1" aria-label={locale === "zh" ? "外观设置" : "Appearance settings"}>
      <button
        className={buttonClass}
        type="button"
        onClick={cycleTheme}
        title={themeTitle}
        aria-label={themeTitle}
        data-theme-preference={preference}
      >
        <ThemeIcon className="h-3.5 w-3.5" />
      </button>
      <button
        className={clsxLike(visualStyle, buttonClass)}
        type="button"
        aria-pressed={visualStyle === "glass"}
        onClick={() => applyStyle(visualStyle === "glass" ? "classic" : "glass")}
        title={locale === "zh" ? (visualStyle === "glass" ? "切换为经典外观" : "切换为玻璃外观") : visualStyle === "glass" ? "Switch to classic appearance" : "Switch to glass appearance"}
      >
        <Sparkles className="h-3.5 w-3.5" />
      </button>
      {showFontScale ? <>
        <button className={buttonClass} type="button" disabled={scaleIndex === 0} onClick={() => setFontScale(SCALES[scaleIndex - 1])} title={locale === "zh" ? "缩小字体" : "Decrease text size"}>
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button className={buttonClass} type="button" disabled={scaleIndex === SCALES.length - 1} onClick={() => setFontScale(SCALES[scaleIndex + 1])} title={locale === "zh" ? "放大字体" : "Increase text size"}>
          <Plus className="h-3.5 w-3.5" />
        </button>
      </> : null}
    </div>
  );
}

export type { FontScale, ThemePreference };
