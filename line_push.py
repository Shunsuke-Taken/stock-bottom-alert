import os
import requests


def push_message(text: str) -> None:
    """
    Push a LINE message using Messaging API (push).
    Required secrets:
      - LINE_CHANNEL_ACCESS_TOKEN
      - LINE_TO_ID
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    to_id = os.getenv("LINE_TO_ID")

    if not token:
        raise RuntimeError("Missing env: LINE_CHANNEL_ACCESS_TOKEN")
    if not to_id:
        raise RuntimeError("Missing env: LINE_TO_ID")

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": to_id,
        "messages": [{"type": "text", "text": text}],
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    # Fail loud if LINE rejects (401/403/etc.)
    r.raise_for_status()
