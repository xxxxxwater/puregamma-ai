from __future__ import annotations

from packages.reports.templates import disclaimer_for


def render_playbook_report(playbooks: list[dict], language: str = "en") -> str:
    if language == "zh":
        body = ["# PureGamma 策略框架", ""]
        for item in playbooks:
            body.extend(
                [
                    f"## {item['strategy_name']}",
                    f"资产：{item['asset']}",
                    f"投资逻辑：{item['thesis']}",
                    f"触发条件：{item['trigger']}",
                    f"失效条件：{item['invalidation']}",
                    "",
                ]
            )
        body.extend(["## 披露", disclaimer_for("zh")])
        return "\n".join(body)
    body = ["# PureGamma Playbooks", ""]
    for item in playbooks:
        body.extend(
            [
                f"## {item['strategy_name']}",
                f"Asset: {item['asset']}",
                f"Thesis: {item['thesis']}",
                f"Trigger: {item['trigger']}",
                f"Invalidation: {item['invalidation']}",
                "",
            ]
        )
    body.extend(["## Disclaimer", disclaimer_for(language)])
    return "\n".join(body)
