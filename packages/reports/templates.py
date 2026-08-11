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


_DISCLAIMERS = {
    "en": (
        "Research only. Not investment advice. PureGamma AI outputs are generated "
        "for informational and educational purposes and may contain errors, stale "
        "data, or incomplete information. Backtest and paper results do not "
        "guarantee future performance. Verify sources independently before acting; "
        "users bear all risks of relying on this content."
    ),
    "zh": (
        "仅供研究，不构成投资建议。PureGamma AI 的输出仅用于信息与教育目的，"
        "可能包含错误、过期数据或不完整信息。回测与模拟结果不代表未来表现。"
        "请独立核实信息来源后再做任何决策，用户需自行承担依赖本内容的全部风险。"
    ),
}


def disclaimer_for(language: str) -> str:
    return _DISCLAIMERS.get(language, _DISCLAIMERS["en"])
