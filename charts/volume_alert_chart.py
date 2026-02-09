"""
Графік для volume alerts (таймфрейм 1h)
"""
import os
import matplotlib.pyplot as plt
from datetime import datetime

from config import CHART_DIR
from charts.level_detector import detect_support_resistance


def build_volume_alert_chart(df, symbol):
    """
    Будує графік для volume alert
    - Таймфрейм: 1h
    - Останні 90 барів
    - Рівні з levels.json (якщо в межах ±10% діапазону)
    - Автовиявлений рівень (зелена лінія)
    - Субграфік з об'ємом
    """
    fig = plt.figure(figsize=(12, 7))

    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.05)
    ax_price = fig.add_subplot(gs[0])
    ax_vol = fig.add_subplot(gs[1], sharex=ax_price)

    # Свічки
    for i, row in df.iterrows():
        color = "green" if row["close"] >= row["open"] else "red"
        ax_price.plot([i, i], [row["low"], row["high"]], color=color, linewidth=1)
        ax_price.bar(
            i,
            abs(row["close"] - row["open"]),
            bottom=min(row["open"], row["close"]),
            color=color,
            width=0.6
        )

    # ✅ ДИНАМІЧНИЙ МАСШТАБ Y (±10%)
    min_price = df["low"].min()
    max_price = df["high"].max()
    price_range = max_price - min_price
    
    y_min = min_price - 0.1 * price_range
    y_max = max_price + 0.1 * price_range
    
    ax_price.set_ylim(y_min, y_max)

    # ✅ Рівні з levels.json (в межах графіка)
    from alerts.levels_manager import load_levels
    levels_map = load_levels()
    all_symbol_levels = levels_map.get(symbol, [])
    
    visible_levels = [lvl for lvl in all_symbol_levels if y_min <= lvl <= y_max]
    
    for lvl in visible_levels:
        ax_price.axhline(lvl, color="blue", linestyle="--", linewidth=1.5, alpha=0.7)

    # ✅ Додаємо вертикальні лінії кожні 15 барів
    total_bars = len(df)
    for i in range(total_bars - 1, -1, -15):
        ax_price.axvline(x=i, color="black", linestyle=":", linewidth=0.5, alpha=0.3)
    
    # ✅ Тікер ЛІВОРУЧ вгорі
    ax_price.text(
        0.02, 0.98, symbol,
        transform=ax_price.transAxes,
        fontsize=16,
        fontweight="bold",
        verticalalignment="top",
        horizontalalignment="left",
        color="white",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="black", alpha=0.7)
    )

    # ✅ Автовиявлений рівень (зелена лінія)
    detected_level = detect_support_resistance(df, tolerance_pct=0.0001)
    detected_level_price = None
    
    if detected_level:
        level_price = detected_level['level']
        if y_min <= level_price <= y_max:
            ax_price.axhline(
                level_price,
                color="limegreen",
                linestyle="--",
                linewidth=2
            )
            detected_level_price = level_price

    # ✅ Рівні ПРАВОРУЧ вгорі (2 рядки)
    if visible_levels or detected_level_price:
        # Рядок 1: Рівні з файлу
        if visible_levels:
            levels_sorted = sorted(set(visible_levels))
            levels_text = ", ".join([f"{lvl:.2f}" for lvl in levels_sorted])
            
            ax_price.text(
                0.98, 0.98, f"Levels: {levels_text}",
                transform=ax_price.transAxes,
                fontsize=9,
                verticalalignment='top',
                horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.6)
            )
        
        # Рядок 2: Виявлений рівень
        y_offset = 0.05 if visible_levels else 0
        if detected_level_price:
            ax_price.text(
                0.98, 0.98 - y_offset, f"Detected: {detected_level_price:.2f}",
                transform=ax_price.transAxes,
                fontsize=9,
                verticalalignment='top',
                horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.6)
            )

    ax_price.set_ylabel("Price (USDT)", fontsize=10)
    ax_price.grid(True, alpha=0.3)
    ax_price.set_xticks([])
    ax_price.set_title(f"{symbol} | 1h | Volume Breakout", fontsize=12, fontweight='bold')

    # ✅ Об'єм (останній бар виділено)
    colors = ["gray"] * (len(df) - 1) + ["orange"]  # Останній бар помаранчевий
    ax_vol.bar(range(len(df)), df["volume_usdt"], color=colors, alpha=0.7)
    ax_vol.set_ylabel("Volume (USDT)", fontsize=10)
    ax_vol.set_xlabel("Time", fontsize=10)
    ax_vol.grid(True, alpha=0.3, axis='y')
    
    # Мітки часу
    step = max(1, len(df) // 10)
    ax_vol.set_xticks(range(0, len(df), step))
    
    time_labels = []
    for i in range(0, len(df), step):
        time_val = df["open_time"].iloc[i]
        if hasattr(time_val, 'strftime'):
            time_labels.append(time_val.strftime('%m-%d %H:%M'))
        else:
            time_labels.append(str(time_val)[:16])
    
    ax_vol.set_xticklabels(time_labels, rotation=45, ha='right', fontsize=8)

    file_path = os.path.join(CHART_DIR, f"{symbol}_volume_alert.png")

    plt.savefig(file_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return file_path