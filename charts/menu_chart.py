"""
Побудова графіків для меню
"""
import matplotlib.pyplot as plt
import os
from datetime import datetime

from config import CHART_DIR


def build_menu_chart(df, symbol, timeframe, detected_level=None, custom_price=None):
    """
    Будує графік для меню зі свічками, об'ємом та рівнями
    """
    fig = plt.figure(figsize=(10, 6))

    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0)
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

    # ✅ ДИНАМІЧНИЙ МАСШТАБ Y
    min_price = df["low"].min()
    max_price = df["high"].max()
    price_range = max_price - min_price
    
    y_min = min_price - 0.1 * price_range
    y_max = max_price + 0.1 * price_range
    
    ax_price.set_ylim(y_min, y_max)

    # ✅ Всі рівні токена (що в діапазоні графіка)
    from alerts.levels_manager import load_levels
    levels_map = load_levels()
    all_symbol_levels = levels_map.get(symbol, [])
    
    visible_levels = [lvl for lvl in all_symbol_levels if y_min <= lvl <= y_max]
    
    for lvl in visible_levels:
        ax_price.axhline(lvl, color="blue", linestyle="--", linewidth=1)

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

    # Виявлений рівень (зелена лінія)
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
            visible_levels.append(level_price)
            detected_level_price = level_price

    # ✅ Custom price (пурпурова лінія)
    if custom_price is not None:
        ax_price.axhline(
            custom_price,
            color="purple",
            linestyle="-",
            linewidth=2
        )
        visible_levels.append(custom_price)

    # ✅ Рівні ПРАВОРУЧ вгорі (2 рядки)
    if visible_levels or detected_level_price:
        # Рядок 1: Рівні з файлу
        file_levels = [lvl for lvl in visible_levels if lvl != detected_level_price and lvl != custom_price]
        if file_levels:
            file_levels_sorted = sorted(set(file_levels))
            file_levels_text = ", ".join([f"{lvl:.2f}" for lvl in file_levels_sorted])
            
            ax_price.text(
                0.98, 0.98, f"Levels: {file_levels_text}",
                transform=ax_price.transAxes,
                fontsize=8,
                verticalalignment='top',
                horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.6)
            )
        
        # Рядок 2: Виявлений рівень
        y_offset = 0.05 if file_levels else 0
        if detected_level_price:
            ax_price.text(
                0.98, 0.98 - y_offset, f"Detected: {detected_level_price:.2f}",
                transform=ax_price.transAxes,
                fontsize=8,
                verticalalignment='top',
                horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.6)
            )

    ax_price.set_ylabel("Price")
    ax_price.grid(True, alpha=0.3)
    ax_price.set_xticks([])

    # Об'єм
    ax_vol.bar(range(len(df)), df["volume"], color="gray", alpha=0.7)
    ax_vol.set_ylabel("Volume")
    ax_vol.set_xlabel("Time")
    
    step = max(1, len(df) // 10)
    ax_vol.set_xticks(range(0, len(df), step))
    
    time_labels = []
    for i in range(0, len(df), step):
        time_val = df["open_time"].iloc[i]
        if hasattr(time_val, 'strftime'):
            time_labels.append(time_val.strftime('%H:%M'))
        else:
            time_labels.append(str(time_val)[11:16])
    
    ax_vol.set_xticklabels(time_labels, rotation=45)

    plt.title(f"{symbol} | {timeframe}", fontsize=12, fontweight='bold')

    filename = os.path.join(
        CHART_DIR,
        f"{symbol}_{timeframe}_{int(datetime.utcnow().timestamp())}.png"
    )

    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close()

    return filename