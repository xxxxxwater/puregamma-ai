from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RelaySettings:
    relay_secret: str = os.getenv("IMESSAGE_RELAY_SECRET", "")
    db_path: str = os.getenv("IMESSAGE_RELAY_DB", "./imessage_relay.sqlite3")
    max_message_length: int = int(os.getenv("IMESSAGE_MAX_MESSAGE_LENGTH", "3000") or 3000)
    max_media_bytes: int = int(os.getenv("IMESSAGE_MAX_MEDIA_BYTES", str(8 * 1024 * 1024)) or 8 * 1024 * 1024)
    replay_tolerance_seconds: int = int(os.getenv("IMESSAGE_REPLAY_TOLERANCE_SECONDS", "300") or 300)
    applescript_path: str = os.getenv(
        "IMESSAGE_APPLESCRIPT_PATH",
        os.path.join(os.path.dirname(__file__), "scripts", "send_imessage.applescript"),
    )
    applescript_file_path: str = os.getenv(
        "IMESSAGE_APPLESCRIPT_FILE_PATH",
        os.path.join(os.path.dirname(__file__), "scripts", "send_imessage_file.applescript"),
    )
    media_work_dir: str = os.getenv("IMESSAGE_MEDIA_WORK_DIR", "/tmp/puregamma-imessage-media")
    agent_api_url: str = os.getenv("IMESSAGE_AGENT_API_URL", "https://api.puregamma.ai").rstrip("/")
    agent_poll_seconds: float = float(os.getenv("IMESSAGE_AGENT_POLL_SECONDS", "3") or 3)


settings = RelaySettings()
