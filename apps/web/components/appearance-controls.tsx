"use client";

import { useEffect, useState } from "react";
import { Minus, Moon, Plus, Sun } from "lucide-react";

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

  useEffect(() => {
    const savedTheme = (localStorage.getItem("pg_theme") as Theme) || "dark";
    const savedScale = (localStorage.getItem("pg_font_scale") as FontScale) || "default";
    setTheme(savedTheme);
    setFontScale(savedScale);
    document.documentElement.dataset.theme = savedTheme;
    document.documentElement.dataset.fontScale = savedScale;
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

  const scaleIndex = scales.indexOf(fontScale);
  const buttonClass = "grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong disabled:opacity-35";

  return (
    <div className="flex items-center gap-1" aria-label={locale === "zh" ? "外观设置" : "Appearance settings"}>
      <button className={buttonClass} type="button" onClick={() => applyTheme(theme === "dark" ? "light" : "dark")} title={locale === "zh" ? "切换明暗主题" : "Toggle theme"}>
        {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
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
