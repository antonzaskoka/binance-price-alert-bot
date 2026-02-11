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
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }

        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        logger.info(f"📤 Sending message to {chat_id}")
        
        r = requests.post(
            f"{TG_API}/sendMessage",
            data=payload,
            timeout=10
        )
        
        if r.status_code != 200:
            logger.error(f"❌ Telegram API error: {r.text}")
        else:
            logger.info(f"✅ Message sent successfully")
        
        return r.json()
    
    except Exception as e:
        logger.error(f"❌ Failed to send message: {e}")
        logger.exception("Full traceback:")
        return None


def send_telegram_photo(chat_id, photo_path, caption):
    """Надсилає фото з підписом"""
    try:
        logger.info(f"📤 Sending photo: {photo_path}")
        
        if not os.path.exists(photo_path):
            logger.error(f"❌ Photo file not found: {photo_path}")
            return
        
        with open(photo_path, "rb") as f:
            r = requests.post(
                f"{TG_API}/sendPhoto",
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                },
                files={"photo": f},
                timeout=20
            )
            
            if r.status_code != 200:
                logger.error(f"❌ Telegram photo API error: {r.text}")
            else:
                logger.info(f"✅ Photo sent successfully")
    
    except Exception as e:
        logger.error(f"❌ Failed to send photo: {e}")
        logger.exception("Full traceback:")


def send_alert_chart(chat_id, symbol, timeframe, chart_path, price, reason):
    """Надсилає графік алерта"""
    logger.info(f"📤 Preparing alert chart for {symbol} {timeframe}")
    
    # Reason вже містить повний текст повідомлення
    caption = reason

    send_telegram_photo(
        chat_id=chat_id,
        photo_path=chart_path,
        caption=caption
    )
    
    logger.info(f"✅ Alert chart sent for {symbol}")


def send_menu_chart(chat_id, chart_path, caption):
    """Надсилає графік з меню"""
    send_telegram_photo(
        chat_id=chat_id,
        photo_path=chart_path,
        caption=caption
    )