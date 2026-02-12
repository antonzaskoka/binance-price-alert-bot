"""
Алерти по зростанню об'єму торгів
"""
import numpy as np
import logging
from datetime import datetime

from database.models import load_hourly_bars, can_alert_volume
from alerts.volume_thresholds import (
    MIN_AVG_VOLUME, VOLUME_THRESHOLDS, VOLUME_ALERT_COOLDOWN_HOURS, ADX_PERIOD
)
from config import RISK_USDT

logger = logging.getLogger(__name__)


def calculate_adx(df, period=14):
    """
    Розраховує ADX (Average Directional Index)
    
    Returns:
        dict: {
            'adx': float,
            'plus_di': float,
            'minus_di': float,
            'adx_prev': float
        }
    """
    if len(df) < period + 1:
        return None
    
    # True Range
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift(1))
    df['low_close'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    
    # Directional Movement
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    
    # Smoothed TR and DM
    atr = df['tr'].rolling(window=period).mean()
    plus_dm_smooth = df['plus_dm'].rolling(window=period).mean()
    minus_dm_smooth = df['minus_dm'].rolling(window=period).mean()
    
    # Directional Indicators
    plus_di = 100 * (plus_dm_smooth / atr)
    minus_di = 100 * (minus_dm_smooth / atr)
    
    # DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    
    current_adx = adx.iloc[-1]
    prev_adx = adx.iloc[-25] if len(adx) >= 25 else adx.iloc[-2]
    
    return {
        'adx': current_adx,
        'plus_di': plus_di.iloc[-1],
        'minus_di': minus_di.iloc[-1],
        'adx_prev': prev_adx
    }


def calculate_ma50(df):
    """Розраховує 50-period Moving Average"""
    if len(df) < 50:
        return None
    
    return df['close'].rolling(window=50).mean().iloc[-1]


def calculate_signal_strength(alert_data):
    """
    Розраховує силу сигналу від 0 до 10
    """
    score = 0
    
    adx = alert_data.get('adx')
    adx_prev = alert_data.get('adx_prev')
    plus_di = alert_data.get('plus_di')
    minus_di = alert_data.get('minus_di')
    ratio = alert_data.get('ratio', 0)
    price = alert_data.get('current_price')
    ma50 = alert_data.get('ma50')
    
    # 1. ADX сила тренду (0-3 бали)
    if adx:
        if adx >= 25:
            score += 3
        elif adx >= 20:
            score += 2
        elif adx >= 15:
            score += 1
    
    # 2. ADX зростання (0-2 бали)
    if adx and adx_prev:
        adx_growth = adx - adx_prev
        if adx_growth >= 10:
            score += 2
        elif adx_growth >= 5:
            score += 1
    
    # 3. Volume ratio (0-3 бали)
    if ratio >= 5:
        score += 3
    elif ratio >= 3:
        score += 2
    elif ratio >= 1.5:
        score += 1
    
    # 4. Directional movement (0-1 бал)
    if plus_di and minus_di and plus_di > minus_di:
        score += 1
    
    # 5. Ціна vs MA50 (0-1 бал)
    if price and ma50 and price > ma50:
        score += 1
    
    return score


def check_volume_threshold(volume_avg_14d, ratio):
    """
    Перевіряє чи співвідношення перевищує поріг для даного середнього об'єму
    """
    for max_avg, min_ratio in VOLUME_THRESHOLDS:
        if volume_avg_14d >= max_avg:
            if ratio >= min_ratio:
                return True
            continue
    
    return False


def check_volume_alert(conn, symbol, cfg):
    """
    Перевіряє алерт по зростанню об'єму (читає готові метрики з БД)
    
    Returns:
        dict або None - дані для алерта
    """
    table = f"kline_{symbol.lower()}_1h"
    
    # ✅ Читаємо останній бар з готовими метриками
    try:
        cursor = conn.execute(f"""
            SELECT open_time_ms, open, volume_24h, volume_avg_14d, ratio
            FROM {table}
            ORDER BY open_time_ms DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        
        if not row:
            return None
        
        open_time_ms, current_price, volume_24h, volume_avg_14d, ratio = row
        
        # Перевіряємо чи є всі дані
        if not volume_24h or not volume_avg_14d or not ratio:
            return None
        
    except Exception as e:
        logger.error(f"Error reading volume metrics for {symbol}: {e}")
        return None
    
    # Фільтр: ігноруємо малоліквідні токени
    if volume_avg_14d < MIN_AVG_VOLUME:
        return None
    
    # Перевіряємо поріг
    if not check_volume_threshold(volume_avg_14d, ratio):
        return None
    
    # Cooldown
    if not can_alert_volume(conn, symbol, VOLUME_ALERT_COOLDOWN_HOURS):
        return None
    
    # Завантажуємо df для ADX та MA50
    df = load_hourly_bars(conn, symbol, limit=100)
    
    if df is None:
        return None
    
    # Розраховуємо ADX
    adx_data = calculate_adx(df, period=ADX_PERIOD)
    
    # Розраховуємо MA50
    ma50 = calculate_ma50(df)
    
    # Розраховуємо зміну ціни за 24h
    if len(df) >= 24:
        price_24h_ago = df["open"].iloc[-24]
        price_change_pct = ((current_price - price_24h_ago) / price_24h_ago) * 100
    else:
        price_change_pct = 0
    
    # Розраховуємо SL та позицію
    sl_small_pct = cfg.get("sl_small_pct", 0.01)
    sl = current_price * sl_small_pct
    position_size = RISK_USDT / sl if sl > 0 else 0
    
    # Шукаємо найближчий рівень
    from alerts.levels_manager import load_levels, find_nearest_level
    levels_map = load_levels()
    symbol_levels = levels_map.get(symbol, [])
    nearest_level = find_nearest_level(symbol_levels, current_price) if symbol_levels else None
    
    alert_data = {
        "symbol": symbol,
        "current_price": current_price,
        "volume_24h": volume_24h,
        "volume_avg_14d": volume_avg_14d,
        "ratio": ratio,
        "price_change_24h_pct": price_change_pct,
        "sl": sl,
        "position_size": position_size,
        "nearest_level": nearest_level,
        "adx": adx_data['adx'] if adx_data else None,
        "adx_prev": adx_data['adx_prev'] if adx_data else None,
        "plus_di": adx_data['plus_di'] if adx_data else None,
        "minus_di": adx_data['minus_di'] if adx_data else None,
        "ma50": ma50,
        "cfg": cfg
    }
    
    # Розраховуємо силу сигналу
    signal_strength = calculate_signal_strength(alert_data)
    alert_data["signal_strength"] = signal_strength
    
    return alert_data


def format_volume_alert(alert_data):
    """Форматує повідомлення для volume alert"""
    symbol = alert_data["symbol"]
    price = alert_data["current_price"]
    volume_24h = alert_data["volume_24h"]
    volume_avg = alert_data["volume_avg_14d"]
    ratio = alert_data["ratio"]
    price_change = alert_data["price_change_24h_pct"]
    sl = alert_data["sl"]
    position = alert_data["position_size"]
    nearest_level = alert_data.get("nearest_level")
    
    # ADX дані
    adx = alert_data.get("adx")
    adx_prev = alert_data.get("adx_prev")
    plus_di = alert_data.get("plus_di")
    minus_di = alert_data.get("minus_di")
    ma50 = alert_data.get("ma50")
    
    # Сила сигналу
    strength = alert_data.get("signal_strength", 0)
    
    # Емоджі для сили сигналу
    if strength >= 8:
        strength_emoji = "🔥🔥🔥"
    elif strength >= 6:
        strength_emoji = "🔥🔥"
    elif strength >= 4:
        strength_emoji = "🔥"
    else:
        strength_emoji = "⚡"
    
    msg = (
        f"📈 {symbol} — VOLUME BREAKOUT\n"
        f"🕒 {datetime.now().strftime('%H:%M:%S')}\n"
        f"{strength_emoji} Signal Strength: {strength}/10\n\n"
        f"💰 Price: {price:.4f}\n"
        f"📊 Price change (24h): {price_change:+.2f}%\n\n"
        f"🔊 Volume 24h: ${volume_24h:,.0f}\n"
        f"📉 Avg volume (14d): ${volume_avg:,.0f}\n"
        f"🚀 Ratio: {ratio:.2f}x\n\n"
    )
    
    # ADX інформація
    if adx:
        adx_growth = adx - adx_prev if adx_prev else 0
        msg += f"📈 ADX: {adx:.1f}"
        if adx_growth > 0:
            msg += f" (↑ {adx_growth:+.1f})"
        msg += "\n"
        
        if plus_di and minus_di:
            msg += f"   +DI: {plus_di:.1f} | -DI: {minus_di:.1f}\n"
    
    if ma50:
        position_vs_ma = "вище" if price > ma50 else "нижче"
        msg += f"📊 MA50: {ma50:.4f} (ціна {position_vs_ma})\n"
    
    msg += (
        f"\n🔻 Stop Loss: ${sl:.4f}\n"
        f"🔺 Position: {position:.4f} {symbol[:-4]}"
    )
    
    # Найближчий рівень
    if nearest_level:
        diff_abs = nearest_level - price
        diff_pct = (diff_abs / price) * 100
        direction = "вище" if diff_abs > 0 else "нижче"
        msg += (
            f"\n\n🔵 Nearest level: {nearest_level:.4f}\n"
            f"   Distance: {abs(diff_pct):.2f}% ({direction}, ${abs(diff_abs):.4f})"
        )
    
    return msg