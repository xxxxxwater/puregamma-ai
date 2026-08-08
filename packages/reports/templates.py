IMESSAGE_DAILY_TEMPLATE = """PureGamma AI Daily Crypto Brief

Market Regime:
{market_regime}

Top Signals:
1. {signal_1}
2. {signal_2}
3. {signal_3}

Risk:
{risk_summary}

Playbook:
{playbook_summary}"""


IMESSAGE_DAILY_TEMPLATE_ZH = """PureGamma AI 每日简报

市场：
{market_regime}

重点信号：
1. {signal_1}
2. {signal_2}
3. {signal_3}

风险：
{risk_summary}

策略框架：
{playbook_summary}

KOL 情绪仅作为输入信号，并非已核实事实。"""


def disclaimer_for(language: str) -> str:
    return ""
