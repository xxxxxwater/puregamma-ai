from __future__ import annotations

from packages.reports.templates import disclaimer_for


def render_event_report(asset: str, event: str, language: str = "en") -> str:
    if language == "zh":
        return f"""# PureGamma 事件报告：{asset}

## 事件
{event}

## 研究视角
将该事件作为情景分析输入，不作为交易指令。

## 披露
{disclaimer_for("zh")}
"""
    return f"""# PureGamma Event Report: {asset}

## Event
{event}

## Research View
Treat this as an input into scenario planning, not as a trade instruction.

## Disclaimer
{disclaimer_for(language)}
"""
