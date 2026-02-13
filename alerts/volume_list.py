"""
Генерує список токенів з зростаючим об'ємом для меню
"""
import logging
from datetime import datetime

from alerts.levels_manager import load_levels

logger = logging.getLogger(__name__)


def get_volume_list(avg_threshold, min_ratio):
    """
    Завантажує готові метрики з БД і фільтрує за volume_24h та ratio
    
    ✅ ВИПРАВЛЕНО: фільтруємо по volume_24h (не avg_14d!)
    
    Args:
        avg_threshold: мінімальний volume_24h (не avg_14d!)
        min_ratio: мінімальний ratio volume_24h / avg_14d

    Returns:
        str: отформатоване повідомлення з списком токенів
    """
    from database.db_manager import get_conn
    
    conn = get_conn()
    levels_map = load_levels()
    
    # Отримуємо список таблиць 1h з БД
    cursor = conn.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        AND name LIKE 'kline_%_1h'
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    
    results = []
    
    for table in tables:
        try:
            symbol = table.replace("kline_", "").replace("_1h", "").upper()
            
            # ✅ Читаємо готові метрики з БД + ДОДАНО high, low, close для NATR
            cursor = conn.execute(f"""
                SELECT open, high, low, close, volume_24h, volume_avg_14d, ratio
                FROM {table}
                ORDER BY open_time_ms DESC
                LIMIT 90
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                continue
            
            # Останній бар
            last_row = rows[0]
            open_price, last_high, last_low, last_close, volume_24h, volume_avg_14d, ratio = last_row
            
            if not volume_24h or not volume_avg_14d or not ratio:
                continue
            
            # ✅ ВИПРАВЛЕНО: фільтр по volume_24h (не avg_14d!)
            if volume_24h < avg_threshold:
                continue
            
            # ✅ ДОДАНО: фільтр проти дрібних монет
            if volume_24h < 1_000_000:
                continue
            
            # Фільтр по ratio
            if ratio < min_ratio:
                continue
            
            # ✅ ДОДАНО: Розраховуємо NATR
            natr = None
            if len(rows) >= 90:
                # Розраховуємо ATR за 90 барів
                atr_sum = 0
                count = 0
                
                for i in range(min(90, len(rows))):
                    _, high, low, close, _, _, _ = rows[i]
                    
                    if i == 0:
                        tr = high - low
                    else:
                        prev_close = rows[i-1][3]
                        tr = max(
                            high - low,
                            abs(high - prev_close),
                            abs(low - prev_close)
                        )
                    
                    atr_sum += tr
                    count += 1
                
                if count > 0:
                    atr = atr_sum / count
                    natr = (atr / last_close) * 100 if last_close > 0 else None
            
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
                "nearest_level": nearest_level,
                "natr": natr  # ✅ ДОДАНО
            })
        
        except Exception as e:
            logger.error(f"Error processing {table}: {e}")
            continue
    
    # Сортуємо по ratio від більшого до меншого
    results.sort(key=lambda x: x["ratio"], reverse=True)
    
    # Формуємо повідомлення
    if not results:
        return "⚠️ Немає токенів з таким фільтром.\n\nПробуй зменшити мультиплікатор або діапазон avg."
    
    # ✅ ВИПРАВЛЕНО: показуємо що фільтруємо по volume_24h
    msg = (
        f"📊 <b>Токени з зростаючим об'ємом</b>\n"
        f"Vol 24h ≥ ${avg_threshold // 1_000_000}M | Ratio ≥ {min_ratio}x\n"
        f"Знайдено: <b>{len(results)}</b> токенів\n"
        f"{'─' * 30}\n\n"
    )
    
    for item in results:
        symbol = item["symbol"]
        ratio = item["ratio"]
        volume_24h = item["volume_24h"]
        open_price = item["open_price"]
        nearest_level = item["nearest_level"]
        natr = item.get("natr")
        
        msg += f"<b>{symbol}</b>\n"
        msg += f"  🚀 Ratio: <b>{ratio:.2f}x</b>\n"
        msg += f"  🔊 Vol 24h: <b>${volume_24h:,.0f}</b>\n"
        msg += f"  💰 Price: <b>{open_price:.4f}</b>\n"
        
        # ✅ ДОДАНО: NATR
        if natr:
            msg += f"  📏 NATR(90): <b>{natr:.2f}%</b>\n"
        
        if nearest_level:
            diff_abs = nearest_level - open_price
            diff_pct = (diff_abs / open_price) * 100
            direction = "↑" if diff_abs > 0 else "↓"
            msg += f"  🔵 Level: <b>{nearest_level:.4f}</b> ({direction} {abs(diff_pct):.2f}%)\n"
        
        msg += "\n"
    
    return msg