import logging

import requests

JOIN_URL = "https://joinjoaomgcd.appspot.com/_ah/api/messaging/v1/sendPush"

log = logging.getLogger(__name__)


def send_notification(
    api_key: str,
    device_id: str,
    title: str,
    author: str,
    price: float,
    target: float,
    condition: str = "",
) -> bool:
    cond_str = f" [{condition}]" if condition else ""
    params = {
        "apikey": api_key,
        "deviceId": device_id,
        "title": f"Bookalert: {title}",
        "text": (
            f"{title} by {author} is available for ${price:.2f}{cond_str} "
            f"(target: ${target:.2f})"
        ),
        "icon": "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/1f4da.png",
    }
    try:
        resp = requests.get(JOIN_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", False):
            log.warning("Join API returned failure: %s", data)
            return False
        return True
    except requests.exceptions.RequestException as e:
        log.error("Failed to send Join notification: %s", e)
        return False
