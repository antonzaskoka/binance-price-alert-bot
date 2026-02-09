"""
Побудова графіків для алертів
"""
import matplotlib.pyplot as plt
import os

from config import CHART_DIR


def build_alert_chart(df, symbol, levels=None):
    """Будує графік алерта зі свічками та рівнями"""
    fig = plt.figure(figsize=(10, 6))
    levels = levels or []

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

    # ✅ Рівні (всі що в діапазоні графіка)
    from alerts.levels_manager import load_levels
    levels_map = load_levels()
    all_symbol_levels = levels_map.get(symbol, [])
    
    visible_levels = [lvl for lvl in all_symbol_levels if y_min <= lvl <= y_max]
    
    for lvl in visible_levels:
        ax_price.axhline(lvl, color="blue", linestyle="--", linewidth=1)
    
    # ✅ Додаємо вертикальні лінії кожні 15 хвилин
    total_bars = len(df)
    for i in range(total_bars - 1, -1, -15):
        ax_price.axvline(x=i, color="black", linestyle=":", linewidth=0.5, alpha=0.9)
    
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

    # ✅ Рівні ПРАВОРУЧ вгорі
    if visible_levels:
        levels_sorted = sorted(set(visible_levels))
        levels_text = ", ".join([f"{lvl:.2f}" for lvl in levels_sorted])
        
        ax_price.text(
            0.98, 0.98, f"Levels: {levels_text}",
            transform=ax_price.transAxes,
            fontsize=8,
            verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.6)
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
        time_val = df["time"].iloc[i]
        if hasattr(time_val, 'strftime'):
            time_labels.append(time_val.strftime('%H:%M'))
        else:
            time_labels.append(str(time_val)[11:16])
    
    ax_vol.set_xticklabels(time_labels, rotation=45)

    file_path = os.path.join(CHART_DIR, f"{symbol}_alert_chart.png")

    plt.savefig(file_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return file_path