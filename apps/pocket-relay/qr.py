from __future__ import annotations

import io

import qrcode


def make_qr(data: str, box_size: int = 8, border: int = 2) -> bytes:
    image = qrcode.make(data, box_size=box_size, border=border)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
