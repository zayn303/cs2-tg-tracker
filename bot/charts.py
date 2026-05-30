import os
from datetime import datetime
from .config import CHARTS_DIR
from .db import get_db, get_preferred_currency

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print('⚠️ matplotlib not available - chart feature disabled')


def generate_chart():
    if not MATPLOTLIB_AVAILABLE:
        return None

    with get_db() as conn:
        pref_currency = get_preferred_currency(conn)
        cur = conn.cursor()
        cur.execute('SELECT date, total_uah, total_usd, total_eur FROM snapshots ORDER BY date')
        rows = cur.fetchall()

    if not rows or len(rows) < 2:
        return False

    currency_config = {
        'UAH': {'idx': 1, 'color': '#34d399', 'symbol': '₴', 'name': 'UAH'},
        'USD': {'idx': 2, 'color': '#00d4ff', 'symbol': '$', 'name': 'USD'},
        'EUR': {'idx': 3, 'color': '#a78bfa', 'symbol': '€', 'name': 'EUR'}
    }

    config = currency_config.get(pref_currency, currency_config['UAH'])

    dates = []
    for row in rows:
        raw = row[0]
        try:
            dates.append(datetime.strptime(raw, '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            dates.append(datetime.strptime(raw, '%Y-%m-%d'))

    values = [row[config['idx']] for row in rows]

    v_min = min(values)
    v_max = max(values)
    v_range = v_max - v_min

    if v_range == 0:
        padding = v_max * 0.02 if v_max > 0 else 1
    else:
        padding = v_range * 0.25

    y_min = v_min - padding
    y_max = v_max + padding

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor('#0f0f1a')
    ax.set_facecolor('#0f0f1a')

    ax.plot(dates, values, color=config['color'], linewidth=3, marker='o', markersize=8,
            markerfacecolor=config['color'], markeredgecolor='white', markeredgewidth=1.5)

    ax.set_ylim(y_min, y_max)

    ax.set_title(f"Portfolio Value History ({config['name']})",
                 fontsize=16, fontweight='bold', color=config['color'], pad=20)
    ax.set_ylabel(f"Value ({config['name']})", color=config['color'], fontsize=14, fontweight='bold')
    ax.set_xlabel('Date', color='white', fontsize=12)
    ax.grid(alpha=0.3, linestyle='--', linewidth=0.5)
    ax.tick_params(axis='y', labelcolor=config['color'], labelsize=11)
    ax.tick_params(axis='x', labelcolor='white', labelsize=10)

    latest_value = values[-1]
    ax.annotate(f"{config['symbol']}{latest_value:,.2f}",
                xy=(dates[-1], latest_value),
                xytext=(15, 15),
                textcoords='offset points',
                fontsize=13,
                fontweight='bold',
                color=config['color'],
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#0f0f1a',
                          edgecolor=config['color'], linewidth=2),
                arrowprops=dict(arrowstyle='->', color=config['color'], lw=1.5))

    if len(values) > 1:
        first_value = values[0]
        if first_value > 0:
            change_pct = ((latest_value - first_value) / first_value) * 100
            change_color = '#34d399' if change_pct >= 0 else '#ef4444'
            change_sign = '+' if change_pct >= 0 else ''

            ax.text(0.02, 0.98, f'{change_sign}{change_pct:.1f}%',
                    transform=ax.transAxes,
                    fontsize=14,
                    fontweight='bold',
                    color=change_color,
                    verticalalignment='top',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='#0f0f1a',
                              edgecolor=change_color, linewidth=2))

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(dates) // 10)))
    plt.xticks(rotation=45, ha='right')

    ax.fill_between(dates, values, y_min, alpha=0.2, color=config['color'])

    plt.tight_layout()
    os.makedirs(CHARTS_DIR, exist_ok=True)
    chart_path = os.path.join(CHARTS_DIR, datetime.now().strftime('%d.%m.%Y-%H:%M') + '.png')
    plt.savefig(chart_path, dpi=120, facecolor='#0f0f1a', edgecolor='none')
    plt.close(fig)

    return chart_path
