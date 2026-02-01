"""
Форматування повідомлень для алертів
"""
from datetime import datetime

from config import RISK_USDT
from alerts.levels_manager import filter_levels_for_range, find_nearest_level


def calculate_atr(df):
    """
    Розраховує середнє значення True Range за останні 90 хвилин
    ATR = mean(max(high-low, |high-prev_close|, |low-prev_close|))
    """
    if df is None or len(df) < 2:
        return 0.0

    true_ranges = []
    for i in range(1, len(df)):
        high = df["high"].iloc[i]
        low = df["low"].iloc[i]
        prev_close = df["close"].iloc[i - 1]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)

    if not true_ranges:
        return 0.0

    return sum(true_ranges) / len(true_ranges)


def format_threshold_alert(alert_data, df):
    """
    Форматує повідомлення для threshold alert (TYPE 1)
    
    Args:
        alert_data: dict з даними алерта
        df: DataFrame з останніми 90 барами для розрахунку ATR
    """
    symbol = alert_data["symbol"]
    price = alert_data["open_price"]          # open останнього бара
    minutes = alert_data["minutes"]
    pct = alert_data["pct"]
    min_price = alert_data["min_price"]
    max_price = alert_data["max_price"]
    threshold_name = alert_data["threshold_name"]
    cfg = alert_data["cfg"]
    levels = alert_data["levels"]

    # Розраховуємо SL та розміри позицій
    sl_small = price * cfg["sl_small_pct"]
    sl_big = price * cfg["sl_big_pct"]

    if sl_small <= 0 or sl_big <= 0:
        return None, None

    size_small_sl = RISK_USDT / sl_small
    size_big_sl = RISK_USDT / sl_big

    # ATR
    atr = calculate_atr(df)

    # Шукаємо найближчий рівень
    valid_levels = filter_levels_for_range(levels, price, 0.05)  # ±5%
    nearest = find_nearest_level(valid_levels, price)

    # Визначаємо назву алерта за діапазоном часу
    if minutes <= 2:
        alert_label = "SMALL RANGE"
    elif minutes <= 20:
        alert_label = "MIDDLE RANGE"
    else:
        alert_label = "LONG RANGE"

    # Формуємо повідомлення
    msg = (
        f"🚨 <b>{symbol}</b>\n"
        f"🕒 {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"📊 {alert_label} Alert ({minutes}m): <b>{pct:.2f}%</b>\n\n"
        f"💰 Price (last bar open): <b>${price:.4f}</b>\n"
        f"📉 Min price ({minutes}m): {min_price:.4f}\n"
        f"📈 Max price ({minutes}m): {max_price:.4f}\n\n"
        f"📐 ATR (90m): <b>${atr:.4f}</b>\n\n"
        f"💲 SL Small: <b>${sl_small:.4f}</b>\n"
        f"🌎🚀 Position (big): <b>{size_small_sl:.4f} {symbol[:-4]}</b>\n\n"
        f"💲💸 SL Big: <b>${sl_big:.4f}</b>\n"
        f"🚀 Position (small): <b>{size_big_sl:.4f} {symbol[:-4]}</b>"
    )

    if nearest:
        diff_abs = nearest - price
        diff_pct = (diff_abs / price) * 100
        msg += (
            f"\n\n🔵 Nearest level: <b>{nearest:.4f}</b>\n"
            f"   Distance: <b>{abs(diff_pct):.2f}%</b> (${diff_abs:.4f})"
        )

    return msg, valid_levels


def format_level_touch_alert(alert_data, df):
    """
    Форматує повідомлення для level touch alert (TYPE 2)
    
    Args:
        alert_data: dict з даними алерта
        df: DataFrame з останніми 90 барами для розрахунку ATR
    """
    symbol = alert_data["symbol"]
    price = alert_data["open_price"]          # open останнього бара
    touched_level = alert_data["touched_level"]
    long_pct = alert_data["long_pct"]
    middle_pct = alert_data["middle_pct"]
    short_pct = alert_data["short_pct"]
    cfg = alert_data["cfg"]
    levels = alert_data["levels"]
    crossed_up = alert_data["crossed_up"]
    crossed_down = alert_data["crossed_down"]

    # Розраховуємо SL та розміри позицій
    sl_small = price * cfg["sl_small_pct"]
    sl_big = price * cfg["sl_big_pct"]

    if sl_small <= 0 or sl_big <= 0:
        return None, None

    size_small_sl = RISK_USDT / sl_small
    size_big_sl = RISK_USDT / sl_big

    # ATR
    atr = calculate_atr(df)

    # Визначаємо дію
    if crossed_up:
        action = "🔼 CROSSED UP"
    elif crossed_down:
        action = "🔽 CROSSED DOWN"
    else:
        action = "🎯 TOUCHED"

    # Фільтруємо рівні для відображення на графіку
    valid_levels = filter_levels_for_range(levels, price, 0.05)  # ±5%

    msg = (
        f"🎯 <b>{symbol}</b> — LEVEL ALERT\n"
        f"🕒 {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"{action} level: <b>{touched_level:.4f}</b>\n\n"
        f"💰 Price (last bar open): <b>{price:.4f}</b>\n\n"
        f"📊 Price movement:\n"
        f"   Long (55m): <b>{long_pct:.2f}%</b>\n"
        f"   Middle (20m): <b>{middle_pct:.2f}%</b>\n"
        f"   Short (2m): <b>{short_pct:.2f}%</b>\n\n"
        f"📐 ATR (90m): <b>${atr:.4f}</b>\n\n"
        f"💲 SL Small: <b>${sl_small:.4f}</b>\n"
        f"🌎🚀 Position (big): <b>{size_small_sl:.4f} {symbol[:-4]}</b>\n\n"
        f"💲💸 SL Big: <b>${sl_big:.4f}</b>\n"
        f"🚀 Position (small): <b>{size_big_sl:.4f} {symbol[:-4]}</b>"
    )

    return msg, valid_levels
