DISCLAIMER = "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
DISCLAIMER_ZH = "使用该服务用户自行承担风险 提供本服务的主体概不负责AI生成所有责任。"


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
{playbook_summary}

Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."""


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

KOL 情绪仅作为输入信号，并非已核实事实。
使用该服务用户自行承担风险 提供本服务的主体概不负责AI生成所有责任。"""


def disclaimer_for(language: str) -> str:
    return DISCLAIMER_ZH if language == "zh" else DISCLAIMER
