"""
Автоматичне виявлення рівнів підтримки/опору
"""
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def detect_support_resistance(df, tolerance_pct=0.0001):
    """
    Виявляє рівні підтримки/опору на основі торкань
    
    Args:
        df: DataFrame з колонками 'high' та 'low'
        tolerance_pct: Толерантність для групування (0.01% = 0.0001)
    
    Returns:
        dict або None: {
            'level': float,
            'touches': int,
            'type': str  # 'support_resistance'
        }
    """
    if df is None or len(df) < 3:
        return None
    
    # Збираємо всі high і low
    prices = []
    
    for idx, row in df.iterrows():
        prices.append(row['high'])
        prices.append(row['low'])
    
    # Створюємо DataFrame для аналізу
    price_df = pd.DataFrame({'price': prices})
    price_df = price_df.sort_values('price').reset_index(drop=True)
    
    # Додаємо bounds
    price_df['lower_bound'] = price_df['price'] * (1 - tolerance_pct)
    price_df['upper_bound'] = price_df['price'] * (1 + tolerance_pct)
    
    # Рахуємо торкання для кожної ціни
    max_touches = 0
    best_level = None
    
    for idx, row in price_df.iterrows():
        price = row['price']
        lower = row['lower_bound']
        upper = row['upper_bound']
        
        # Рахуємо скільки цін потрапляють в діапазон
        touches = ((price_df['price'] >= lower) & (price_df['price'] <= upper)).sum()
        
        if touches > max_touches:
            max_touches = touches
            best_level = price
    
    # Перевіряємо, чи є достатньо торкань
    if max_touches >= 3:
        return {
            'level': best_level,
            'touches': max_touches,
            'type': 'support_resistance'
        }
    
    return None


def format_detected_level_info(detected_level, current_price):
    """
    Форматує інформацію про виявлений рівень
    
    Returns:
        str: текст для додавання до caption
    """
    if not detected_level:
        return ""
    
    level = detected_level['level']
    touches = detected_level['touches']
    
    diff_abs = level - current_price
    diff_pct = (diff_abs / current_price) * 100
    
    direction = "вище" if diff_abs > 0 else "нижче"
    
    text = (
        f"\n\n🟢 Виявлено рівень: <b>{level:.4f}</b>\n"
        f"   Торкань: {touches}\n"
        f"   Відстань: <b>{abs(diff_pct):.2f}%</b> ({direction}, ${abs(diff_abs):.4f})"
    )
    
    return text