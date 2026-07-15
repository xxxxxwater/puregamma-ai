from packages.billing.metering import quote_credits
from packages.config.secret_store import SecretStore


def test_quote_respects_luna_and_task_bounds():
    short = quote_credits(task_type="agent_chat_basic", resolved_model="default", input_tokens=10)
    luna = quote_credits(task_type="agent_luna_research", requested_model="gpt-5.6-luna", resolved_model="gpt-5.6-luna", input_tokens=4000, output_tokens=4000, tool_calls=["deep_research"])
    assert short.credits >= 2
    assert luna.credits >= 6
    assert luna.credits <= 100
    assert luna.resolved_model == "gpt-5.6-luna"


def test_quote_attachment_and_notification_are_metered():
    quote = quote_credits(task_type="imessage_alert", notification_channel="imessage", attachment_bytes=20481)
    assert quote.credits == 2  # fixed notification task cap prevents runaway attachment charges


def test_secret_store_encrypts_with_unique_nonce_and_rotates():
    first = SecretStore("a" * 32)
    second = SecretStore("b" * 32, key_version="v2")
    one = first.encrypt("exchange-token")
    two = first.encrypt("exchange-token")
    assert one["nonce"] != two["nonce"]
    assert first.decrypt(one) == "exchange-token"
    rotated = first.rotate(one, second)
    assert second.decrypt(rotated) == "exchange-token"
