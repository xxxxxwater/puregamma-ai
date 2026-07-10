from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RelaySettings:
    relay_secret: str = os.getenv("IMESSAGE_RELAY_SECRET", "")
    db_path: str = os.getenv("IMESSAGE_RELAY_DB", "./imessage_relay.sqlite3")
    max_message_length: int = int(os.getenv("IMESSAGE_MAX_MESSAGE_LENGTH", "3000") or 3000)
    replay_tolerance_seconds: int = int(os.getenv("IMESSAGE_REPLAY_TOLERANCE_SECONDS", "300") or 300)
    applescript_path: str = os.getenv(
        "IMESSAGE_APPLESCRIPT_PATH",
        os.path.join(os.path.dirname(__file__), "scripts", "send_imessage.applescript"),
    )


settings = RelaySettings()
