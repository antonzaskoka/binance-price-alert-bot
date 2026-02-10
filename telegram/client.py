"""
Telegram API клієнт
"""
import os
import requests
import json
import logging

from config import TG_API

logger = logging.getLogger(__name__)


# def send_telegram_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
#     """Надсилає текстове повідомлення"""
#     payload = {
#         "chat_id": chat_id,
#         "text": text,
#         "parse_mode": parse_mode
#     }

#     if reply_markup:
#         payload["reply_markup"] = json.dumps(reply_markup)

#     r = requests.post(
#         f"{TG_API}/sendMessage",
#         data=payload,
#         timeout=10
#     )
#     return r.json()


def send_telegram_message(chat_id, text, reply_markup=None):
    """Відправляє текстове повідомлення"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from config import TG_API
        import requests
        
        logger.info(f"📤 Sending message to {chat_id}: {text[:50]}...")
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        
        response = requests.post(
            f"{TG_API}/sendMessage",
            json=payload,
            timeout=10
        )
        
        logger.info(f"📤 Telegram response: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"❌ Telegram API error: {response.text}")
            return
        
        logger.info(f"✅ Message sent successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to send message: {e}")
        logger.exception("Full traceback:")


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


# def send_alert_chart(chat_id, symbol, timeframe, chart_path, price, reason):
#     """Надсилає графік алерта"""
#     # Reason вже містить повний текст повідомлення
#     caption = reason

#     send_telegram_photo(
#         chat_id=chat_id,
#         photo_path=chart_path,
#         caption=caption
#    )
def send_alert_chart(chat_id, symbol, timeframe, chart_path, price, reason):
    """Відправляє алерт з графіком"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"📤 Preparing to send chart: {chart_path}")
        
        # Перевіряємо чи файл існує
        import os
        if not os.path.exists(chart_path):
            logger.error(f"❌ Chart file not found: {chart_path}")
            return
        
        logger.info(f"📤 Opening chart file...")
        with open(chart_path, "rb") as photo:
            logger.info(f"📤 Sending photo to Telegram (chat_id={chat_id})...")
            
            from config import TG_API
            import requests
            
            response = requests.post(
                f"{TG_API}/sendPhoto",
                data={
                    "chat_id": chat_id,
                    "caption": reason,
                    "parse_mode": "HTML"
                },
                files={"photo": photo},
                timeout=30
            )
            
            logger.info(f"📤 Telegram response: {response.status_code}")
            logger.info(f"📤 Response body: {response.text}")
            
            if response.status_code != 200:
                logger.error(f"❌ Telegram API error: {response.text}")
                return
            
            logger.info(f"✅ Chart sent successfully to {chat_id}")
            
    except Exception as e:
        logger.error(f"❌ Failed to send chart: {e}")
        logger.exception("Full traceback:")


def send_menu_chart(chat_id, chart_path, caption):
    """Надсилає графік з меню"""
    send_telegram_photo(
        chat_id=chat_id,
        photo_path=chart_path,
        caption=caption
    )