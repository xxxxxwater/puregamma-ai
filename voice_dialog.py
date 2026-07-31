#!/usr/bin/env python3
"""Small production smoke-test client for the fixed PureGamma secretary voice."""

import argparse
import os
from pathlib import Path

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text")
    parser.add_argument("--output", default="secretary-voice.mp3")
    args = parser.parse_args()
    key = os.environ.get("NOIZ_API_KEY", "").strip()
    if not key:
        raise SystemExit("NOIZ_API_KEY is not configured")
    response = requests.post(
        "https://noiz.ai/v1/text-to-speech",
        headers={"Authorization": key},
        data={"text": args.text, "voice_id": os.getenv("NOIZ_VOICE_ID", "183203aa0"), "output_format": "mp3", "speed": "0.96"},
        timeout=120,
    )
    response.raise_for_status()
    Path(args.output).write_bytes(response.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
