"""
Налаштування порогів для volume alerts
"""

# Мінімальний середній об'єм (ігноруємо токени менше 1М)
MIN_AVG_VOLUME = 1_000_000

# Драбинка умов: (max_avg_volume, min_ratio)
# Сортувати від більшого до меншого!
VOLUME_THRESHOLDS = [
    (100_000_000, 2.0),   # ✅ Якщо vol_24h >= 100М → потрібен ratio >= 2.0x
    (50_000_000, 3.0),    # ✅ Якщо vol_24h >= 50М  → потрібен ratio >= 3.0x
    (30_000_000, 5.0),    # ✅ Якщо vol_24h >= 30М  → потрібен ratio >= 5.0x
    (10_000_000, 10.0),   # ✅ Якщо vol_24h >= 10М  → потрібен ratio >= 10.0x
    (0, 15.0),            # ✅ Інакше               → потрібен ratio >= 15.0x
]

# Cooldown між алертами (години)
VOLUME_ALERT_COOLDOWN_HOURS = 6

# ADX налаштування
ADX_PERIOD = 14  # Період для розрахунку ADX
ADX_STRONG_TREND = 25  # ADX > 25 = сильний тренд
ADX_MODERATE_TREND = 20  # ADX 20-25 = помірний тренд
ADX_WEAK_TREND = 15  # ADX 15-20 = слабкий тренд

# Moving Average для фільтру тренду
MA_PERIOD = 50  # 50-період MA