"""
Telegram API клієнт
"""
import os
import requests
import json
import logging

from config import TG_API

logger = logging.getLogger(__name__)


def send_telegram_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """Надсилає текстове повідомлення"""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    r = requests.post(
        f"{TG_API}/sendMessage",
        data=payload,
        timeout=10
    )
    return r.json()


def send_telegram_photo(chat_id, photo_path, caption):
    """Надсилає фото з підписом"""
    with open(photo_path, "rb") as f:
        requests.post(
            f"{TG_API}/sendPhoto",
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML"
            },
            files={"photo": f},
            timeout=20
        )


def send_alert_chart(chat_id, symbol, timeframe, chart_path, price, reason):
    """Надсилає графік алерта"""
    # Reason вже містить повний текст повідомлення
    caption = reason

    send_telegram_photo(
        chat_id=chat_id,
        photo_path=chart_path,
        caption=caption
    )


def send_menu_chart(chat_id, chart_path, caption):
    """Надсилає графік з меню"""
    send_telegram_photo(
        chat_id=chat_id,
        photo_path=chart_path,
        caption=caption
    )