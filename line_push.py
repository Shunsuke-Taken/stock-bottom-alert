import os
import requests

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_TO_ID = os.environ["LINE_TO_ID"]

def line_push(message: str) -> None:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"to": LINE_TO_ID, "messages": [{"type": "text", "text": message}]}
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
