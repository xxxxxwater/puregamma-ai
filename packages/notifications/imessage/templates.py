from __future__ import annotations

from packages.reports.templates import IMESSAGE_DAILY_TEMPLATE, IMESSAGE_DAILY_TEMPLATE_ZH


def daily_imessage(market_regime: str, signals: list[str], risk_summary: str, playbook_summary: str, language: str = "en") -> str:
    padded = (signals + [("无信号" if language == "zh" else "No signal")] * 3)[:3]
    template = IMESSAGE_DAILY_TEMPLATE_ZH if language == "zh" else IMESSAGE_DAILY_TEMPLATE
    return template.format(
        market_regime=market_regime,
        signal_1=padded[0],
        signal_2=padded[1],
        signal_3=padded[2],
        risk_summary=risk_summary,
        playbook_summary=playbook_summary,
    )
