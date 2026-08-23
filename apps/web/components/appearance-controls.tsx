"use client";

import { useEffect, useState } from "react";
import { Minus, Moon, Plus, Sparkles, Sun } from "lucide-react";
import { applyVisualStyle, readVisualStyle, type VisualStyle } from "@/lib/visual-style";

type Theme = "dark" | "light";
type FontScale = "compact" | "default" | "large";

const scales: FontScale[] = ["compact", "default", "large"];

export function AppearanceControls({
  locale,
  showFontScale = true,
}: {
  locale: "en" | "zh";
  showFontScale?: boolean;
}) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [fontScale, setFontScale] = useState<FontScale>("default");
  const [visualStyle, setVisualStyle] = useState<VisualStyle>("glass");

  useEffect(() => {
    const savedTheme = (localStorage.getItem("pg_theme") as Theme) || "dark";
    const savedScale = (localStorage.getItem("pg_font_scale") as FontScale) || "default";
    const savedStyle = readVisualStyle();
    setTheme(savedTheme);
    setFontScale(savedScale);
    setVisualStyle(savedStyle);
    document.documentElement.dataset.theme = savedTheme;
    document.documentElement.dataset.fontScale = savedScale;
    applyVisualStyle(savedStyle);
  }, []);

  const applyTheme = (value: Theme) => {
    setTheme(value);
    localStorage.setItem("pg_theme", value);
    document.documentElement.dataset.theme = value;
  };

  const applyScale = (value: FontScale) => {
    setFontScale(value);
    localStorage.setItem("pg_font_scale", value);
    document.documentElement.dataset.fontScale = value;
  };

  const applyStyle = (value: VisualStyle) => {
    setVisualStyle(value);
    applyVisualStyle(value);
  };

  const scaleIndex = scales.indexOf(fontScale);
  const buttonClass = "grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong disabled:opacity-35";

  return (
    <div className="flex items-center gap-1" aria-label={locale === "zh" ? "外观设置" : "Appearance settings"}>
      <button className={buttonClass} type="button" onClick={() => applyTheme(theme === "dark" ? "light" : "dark")} title={locale === "zh" ? "切换明暗主题" : "Toggle theme"}>
        {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
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
        <button className={buttonClass} type="button" disabled={scaleIndex === 0} onClick={() => applyScale(scales[scaleIndex - 1])} title={locale === "zh" ? "缩小字体" : "Decrease text size"}>
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button className={buttonClass} type="button" disabled={scaleIndex === scales.length - 1} onClick={() => applyScale(scales[scaleIndex + 1])} title={locale === "zh" ? "放大字体" : "Increase text size"}>
          <Plus className="h-3.5 w-3.5" />
        </button>
      </> : null}
    </div>
  );
}

function clsxLike(visualStyle: VisualStyle, base: string): string {
  // The glass style is the default: highlight the control only when the
  // user switched away, keeping the same visual language as other toggles.
  return visualStyle === "classic" ? `${base} border-border-pg-strong` : base;
}
