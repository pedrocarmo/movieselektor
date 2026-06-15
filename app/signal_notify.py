"""Post a message (with optional image attachment) to a Signal group via signal-cli-rest-api."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

import httpx

from . import config

log = logging.getLogger(__name__)


async def send(text: str, image_path: Optional[Path] = None) -> bool:
    """POST to /v2/send. Returns True on success, False on any failure. Never raises."""
    if not (config.SIGNAL_API_URL and config.SIGNAL_SENDER_NUMBER and config.SIGNAL_GROUP_ID):
        return False

    payload: dict = {
        "message": text,
        "number": config.SIGNAL_SENDER_NUMBER,
        "recipients": [config.SIGNAL_GROUP_ID],
    }

    if image_path and image_path.exists():
        payload["base64_attachments"] = [base64.b64encode(image_path.read_bytes()).decode()]

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=30.0, pool=5.0)) as client:
            resp = await client.post(f"{config.SIGNAL_API_URL}/v2/send", json=payload)
            if not resp.is_success:
                log.warning("Signal send failed: %s — %s", resp.status_code, resp.text)
                return False
        return True
    except Exception as exc:
        log.warning("Signal send failed (%s): %s", type(exc).__name__, exc)
        return False
