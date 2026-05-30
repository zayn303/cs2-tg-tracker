from datetime import datetime, timedelta
from typing import Optional
from .db import get_db


def calculate_change(current: float, days_ago: int, date_today: str) -> Optional[float]:
    with get_db() as conn:
        cur = conn.cursor()
        cutoff = (datetime.strptime(date_today, '%Y-%m-%d') - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        cur.execute('''
            SELECT total_uah FROM snapshots
            WHERE date <= ?
            ORDER BY date DESC
            LIMIT 1
        ''', (cutoff + ' 23:59:59',))
        row = cur.fetchone()

    if row and row[0] and row[0] > 0:
        return ((current - row[0]) / row[0]) * 100
    return None


def format_change(change: Optional[float]) -> str:
    if change is None:
        return '—'
    emoji = '🟢' if change >= 0 else '🔴'
    sign = '+' if change >= 0 else ''
    return f'{emoji} {sign}{change:.1f}%'


def build_items_report(item_data: list, date_today: str) -> str:
    lines = ['🏷 <b>Items by total value</b>']

    sorted_items = sorted(item_data, key=lambda x: x['price_uah'] * x['qty'], reverse=True)

    for item in sorted_items:
        if item['price_usd'] <= 0:
            continue

        name = item['name']
        qty = item['qty']
        uah = item['price_uah']
        usd = item['price_usd']
        eur = item['price_eur']

        def item_change(days, _name=name, _uah=uah):
            cutoff = (datetime.strptime(date_today, '%Y-%m-%d') - timedelta(days=days)).strftime('%Y-%m-%d')
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute('''
                    SELECT price_uah FROM item_prices
                    WHERE name = ? AND date <= ?
                    ORDER BY date DESC LIMIT 1
                ''', (_name, cutoff + ' 23:59:59'))
                row = cur.fetchone()
            if row and row[0] and row[0] > 0:
                return ((_uah - row[0]) / row[0]) * 100
            return None

        c24 = format_change(item_change(1))
        c7  = format_change(item_change(7))
        c30 = format_change(item_change(30))

        unit_line = f"  ₴{uah:.2f} / ${usd:.2f} / €{eur:.2f}"

        if qty > 1:
            total_uah_i = uah * qty
            total_usd_i = usd * qty
            total_eur_i = eur * qty
            lines.extend([
                '',
                f"• {qty}× {name}",
                f"{unit_line} ea.",
                f"  = ₴{total_uah_i:,.2f} / ${total_usd_i:,.2f} / €{total_eur_i:,.2f}",
                f"  24h: {c24}  7d: {c7}  30d: {c30}"
            ])
        else:
            lines.extend([
                '',
                f"• {name}",
                unit_line,
                f"  24h: {c24}  7d: {c7}  30d: {c30}"
            ])

    return '\n'.join(lines)
