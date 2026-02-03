"""
Генерує список токенів з зростаючим об'ємом для меню
"""
import logging
from datetime import datetime

from alerts.levels_manager import load_levels

logger = logging.getLogger(__name__)


def get_volume_list(avg_threshold, min_ratio):
    """
    Завантажує годинні дані для всіх токенів і фільтрує за avg та ratio.

    Args:
        avg_threshold: мінімальний volume_avg_14d
        min_ratio: мінімальний ratio volume_24h / avg_14d

    Returns:
        str: отформатоване повідомлення з списком токенів
    """
    from database.db_manager import get_conn
    from alerts.volume_alert import calculate_volume_usdt, calculate_volume_metrics
    from database.models import load_hourly_bars

    conn = get_conn()

    # Отримуємо рівні
    levels_map = load_levels()

    # Отримуємо список таблиць 1h з БД
    cursor = conn.execute(
        """
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        AND name LIKE 'kline_%_1h'
        """
    )
    tables = [row[0] for row in cursor.fetchall()]

    # Парсимо символи з назв таблиць: kline_btcusdt_1h -> BTCUSDT
    symbols = []
    for t in tables:
        sym = t.replace("kline_", "").replace("_1h", "").upper()
        symbols.append(sym)

    results = []

    for symbol in symbols:
        try:
            df = load_hourly_bars(conn, symbol, limit=400)
            if df is None or len(df) < 24:
                continue

            df = calculate_volume_usdt(df)
            metrics = calculate_volume_metrics(df)

            if not metrics:
                continue

            volume_24h = metrics["volume_24h"]
            volume_avg_14d = metrics["volume_avg_14d"]
            ratio = metrics["ratio"]

            # Фільтр по avg
            if volume_avg_14d < avg_threshold:
                continue

            # Фільтр по ratio
            if ratio < min_ratio:
                continue

            # Ціна відкриття останнього бара
            open_price = df["open"].iloc[-1]

            # Найближчий рівень
            symbol_levels = levels_map.get(symbol, [])
            nearest_level = None
            if symbol_levels:
                nearest_level = min(symbol_levels, key=lambda lvl: abs(lvl - open_price))

            results.append({
                "symbol": symbol,
                "ratio": ratio,
                "volume_24h": volume_24h,
                "volume_avg_14d": volume_avg_14d,
                "open_price": open_price,
                "nearest_level": nearest_level
            })

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            continue

    # Сортуємо по ratio від більшого до меншого
    results.sort(key=lambda x: x["ratio"], reverse=True)

    # Формуємо повідомлення
    if not results:
        return "⚠️ Немає токенів з таким фільтром.\n\nПробуй зменшити мультиплікатор або діапазон avg."

    msg = (
        f"📊 <b>Токени з зростаючим об'ємом</b>\n"
        f"Avg ≥ ${avg_threshold // 1_000_000}M | Ratio ≥ {min_ratio}x\n"
        f"Знайдено: <b>{len(results)}</b> токенів\n"
        f"{'─' * 30}\n\n"
    )

    for item in results:
        symbol = item["symbol"]
        ratio = item["ratio"]
        volume_24h = item["volume_24h"]
        open_price = item["open_price"]
        nearest_level = item["nearest_level"]

        msg += f"<b>{symbol}</b>\n"
        msg += f"  🚀 Ratio: <b>{ratio:.2f}x</b>\n"
        msg += f"  🔊 Vol 24h: <b>${volume_24h:,.0f}</b>\n"
        msg += f"  💰 Price: <b>{open_price:.4f}</b>\n"

        if nearest_level:
            diff_abs = nearest_level - open_price
            diff_pct = (diff_abs / open_price) * 100
            direction = "↑" if diff_abs > 0 else "↓"
            msg += f"  🔵 Level: <b>{nearest_level:.4f}</b> ({direction} {abs(diff_pct):.2f}%)\n"

        msg += "\n"

    return msg
