import time
import json
import schedule
from datetime import datetime, timezone
from .config import DELAY
from .db import get_db
from .steam import get_current_price, check_steam_up
from .currency import get_exchange_rates
from .telegram import send_message
from .reports import calculate_change, format_change


def daily_update():
    print(f'▶ Starting daily update at {datetime.now(timezone.utc).isoformat()}')

    if not check_steam_up():
        print('⚠️ Steam API unreachable, skipping update')
        return

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT name, qty FROM watchlist')
        watchlist = cur.fetchall()

        if not watchlist:
            print('⚠️ Watchlist empty, skipping update')
            return

        print(f'📊 Fetching prices for {len(watchlist)} items')

        rates = get_exchange_rates()
        print(f"💱 Rates: 1 USD = ₴{rates['uah_per_usd']:.2f} ({rates['source']})")

        item_data = []
        current_delay = DELAY
        consecutive_failures = 0

        for i, (name, qty) in enumerate(watchlist, 1):
            print(f'[{i}/{len(watchlist)}] {qty}× {name}')
            price_usd, was_rate_limited = get_current_price(name)

            if was_rate_limited:
                # After a 429 mid-run, back off inter-item delay for the rest of the run
                current_delay = max(current_delay, 8.0)
                print(f'  ℹ️ Rate limited during fetch — inter-item delay increased to {current_delay}s')

            if price_usd is None:
                consecutive_failures += 1
                cur.execute(
                    'SELECT price_usd FROM item_prices WHERE name=? AND price_usd > 0 ORDER BY date DESC LIMIT 1',
                    (name,)
                )
                row = cur.fetchone()
                price_usd = row[0] if row else 0.0
                if price_usd:
                    print(f'  ⚠️ Using cached price ${price_usd:.4f} for {name}')

                # 2+ consecutive failures likely means Steam is throttling hard — pause 90s
                if consecutive_failures >= 2:
                    print(f'  ⏸ {consecutive_failures} consecutive failures — pausing 90s to let Steam cool down')
                    time.sleep(90)
                    consecutive_failures = 0
                    current_delay = max(current_delay, 8.0)
            else:
                consecutive_failures = 0

            item_data.append({
                'name': name,
                'qty': qty,
                'price_usd': price_usd,
                'price_uah': price_usd * rates['uah_per_usd'],
                'price_eur': price_usd * rates['eur_per_usd']
            })
            time.sleep(current_delay)

        date_today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        datetime_now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        total_uah = sum(item['price_uah'] * item['qty'] for item in item_data)
        total_usd = sum(item['price_usd'] * item['qty'] for item in item_data)
        total_eur = sum(item['price_eur'] * item['qty'] for item in item_data)
        total_items = sum(item['qty'] for item in item_data)

        if total_usd == 0:
            print('⚠️ All prices returned 0 — likely network failure. Skipping snapshot.')
            send_message('⚠️ Price update skipped — all items returned $0 (network unreachable?)')
            return

        cur.execute('''
            INSERT INTO snapshots (date, total_uah, total_usd, total_eur, item_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime_now, total_uah, total_usd, total_eur, total_items))

        for item in item_data:
            cur.execute('''
                INSERT INTO item_prices (date, name, qty, price_uah, price_usd, price_eur)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (datetime_now, item['name'], item['qty'],
                  item['price_uah'], item['price_usd'], item['price_eur']))

        conn.commit()

    change_24h = calculate_change(total_uah, 1, date_today)
    change_7d  = calculate_change(total_uah, 7, date_today)
    change_30d = calculate_change(total_uah, 30, date_today)

    chain_eur = rates.get('chain_eur_per_usd')
    market_eur = rates['market_eur_per_usd']
    if chain_eur:
        spread = (chain_eur - market_eur) / market_eur * 100
        spread_emoji = '🟢' if spread >= -1.5 else ('🟡' if spread >= -3.0 else '🔴')
        eur_line = (f"💶 USD→EUR: €{chain_eur:.4f} chain / €{market_eur:.4f} mkt  "
                    f"{spread_emoji} {spread:+.2f}%")
    else:
        eur_line = f"💶 USD→EUR: €{market_eur:.4f} (mkt only)"

    summary = '\n'.join([
        '📊 <b>Market Report</b>',
        f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        f'📋 {total_items} items ({len(item_data)} unique)',
        '',
        '💰 <b>Total value</b>',
        f'   ₴{total_uah:,.2f} UAH',
        f'   ${total_usd:,.2f} USD',
        f'   €{total_eur:,.2f} EUR',
        '',
        '📈 <b>Portfolio changes</b>',
        f'   24h: {format_change(change_24h)}',
        f'   7d:  {format_change(change_7d)}',
        f'   30d: {format_change(change_30d)}',
        '',
        f"💱 UAH: ₴{rates['uah_per_usd']:.2f}/USD ({rates['source']})",
        eur_line,
    ])

    keyboard = {
        'inline_keyboard': [[
            {'text': '🏷 Show Items', 'callback_data': 'items_detail'},
            {'text': '📊 Chart',      'callback_data': 'chart'},
            {'text': '💱 Rates',      'callback_data': 'rates'},
            {'text': '🔄 Refresh',    'callback_data': 'refresh'}
        ]]
    }

    send_message(summary, reply_markup=keyboard)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                    ('last_item_data', json.dumps({'date': date_today, 'items': item_data})))
        conn.commit()

    print('✅ Daily update complete')


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)
