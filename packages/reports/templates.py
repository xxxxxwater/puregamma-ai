DISCLAIMER = "This is not financial advice."
DISCLAIMER_ZH = "本内容仅供信息和研究参考，不构成投资建议。"


IMESSAGE_DAILY_TEMPLATE = """PureGamma.ai Daily Crypto Brief

Market Regime:
{market_regime}

Top Signals:
1. {signal_1}
2. {signal_2}
3. {signal_3}

Risk:
{risk_summary}

Playbook:
{playbook_summary}

This is not financial advice."""


IMESSAGE_DAILY_TEMPLATE_ZH = """PureGamma.ai 每日简报

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

KOL 情绪仅作为输入信号，并非已核实事实。
本内容仅供信息和研究参考，不构成投资建议。"""


def disclaimer_for(language: str) -> str:
    return DISCLAIMER_ZH if language == "zh" else DISCLAIMER
