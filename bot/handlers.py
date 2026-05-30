import sqlite3
import time
import urllib.parse
from datetime import datetime, timezone
from .config import session
from .db import get_db, get_preferred_currency, set_preferred_currency
from .telegram import send_message, send_photo
from .steam import get_current_price, check_steam_up, resolve_steam_id
from .reports import build_items_report
from .charts import generate_chart, MATPLOTLIB_AVAILABLE
from .currency import get_exchange_rates
from .scheduler import daily_update


def handle_add(text: str):
    parts = text.strip().split()

    if not parts:
        send_message('❌ Usage: /add &lt;url&gt; [quantity]\nExample: /add https://... 5')
        return

    url = parts[0]
    qty = 1

    if len(parts) > 1:
        try:
            qty = int(parts[1])
            if qty < 1:
                send_message('❌ Quantity must be at least 1')
                return
        except ValueError:
            send_message('❌ Invalid quantity. Must be a number.\nExample: /add https://... 5')
            return

    if '/listings/730/' not in url:
        send_message('❌ Invalid URL. Must be a Steam Market URL (730).')
        return

    name = url.split('/listings/730/')[-1].split('?')[0].rstrip('/')
    name = urllib.parse.unquote(name)

    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO watchlist (name, qty, added_at) VALUES (?, ?, ?)',
                        (name, qty, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            send_message(f'✅ Added to watchlist:\n<code>{name}</code>\nQuantity: {qty}')
        except sqlite3.IntegrityError:
            cur.execute('UPDATE watchlist SET qty = ? WHERE name = ?', (qty, name))
            conn.commit()
            send_message(f'✅ Updated quantity:\n<code>{name}</code>\nQuantity: {qty}')


def handle_remove(fragment: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT name FROM watchlist WHERE name LIKE ? LIMIT 1',
                    (f'%{fragment}%',))
        row = cur.fetchone()

        if row:
            cur.execute('DELETE FROM watchlist WHERE name = ?', (row[0],))
            conn.commit()
            send_message(f'🗑 Removed:\n<code>{row[0]}</code>')
        else:
            send_message(f'❌ No item found matching: {fragment}')


def handle_list():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT name, qty FROM watchlist ORDER BY added_at DESC')
        items = cur.fetchall()

    if items:
        total_items = sum(qty for _, qty in items)
        pref_currency = get_preferred_currency()
        msg = f'📋 <b>Watchlist ({len(items)} unique, {total_items} total)</b>\n'
        msg += f'💱 Preferred currency: <b>{pref_currency}</b>\n\n'
        for name, qty in items:
            msg += f'• {qty}× {name}\n' if qty > 1 else f'• {name}\n'

        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '📋 Report',  'callback_data': 'report'},
                    {'text': '📊 Chart',   'callback_data': 'chart'},
                    {'text': '🔄 Refresh', 'callback_data': 'refresh'}
                ],
                [
                    {'text': '💱 Rates', 'callback_data': 'rates'},
                    {'text': 'UAH', 'callback_data': 'curr_UAH'},
                    {'text': 'USD', 'callback_data': 'curr_USD'},
                    {'text': 'EUR', 'callback_data': 'curr_EUR'}
                ]
            ]
        }
        send_message(msg, reply_markup=keyboard)
    else:
        send_message('📭 Watchlist is empty!\nUse /add &lt;url&gt; [qty] to track items.')


def handle_scan(steam_input: str):
    steam_input = steam_input.strip()
    if not steam_input:
        send_message('❌ Usage: /scan &lt;steamid64 or vanity name or profile URL&gt;\nExample: /scan zaynplayersteam')
        return

    if not check_steam_up():
        send_message('❌ Steam servers appear down. Try again later.')
        return

    steam_id = resolve_steam_id(steam_input)
    if not steam_id:
        send_message(f'❌ Could not resolve <code>{steam_input}</code> to a Steam ID. Check the name/URL.')
        return

    send_message(f'🔍 Scanning inventory for <code>{steam_id}</code>...')

    inv_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://steamcommunity.com/my/inventory/',
        'Origin': 'https://steamcommunity.com',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    inv_url = f'https://steamcommunity.com/inventory/{steam_id}/730/2'

    all_assets = []
    all_descriptions = []
    start_assetid = None

    while True:
        params = {'l': 'english', 'count': 2000}
        if start_assetid:
            params['start_assetid'] = start_assetid

        page_data = None
        last_error = None
        for attempt in range(3):
            try:
                resp = session.get(inv_url, params=params, headers=inv_headers, timeout=15)
                if resp.status_code == 403:
                    send_message('❌ Inventory is private. Set Steam → Privacy Settings → Inventory → Public.')
                    return
                if resp.status_code == 429:
                    last_error = 'rate limited'
                    if attempt < 2:
                        time.sleep(5)
                    continue
                if resp.status_code != 200:
                    last_error = f'HTTP {resp.status_code}'
                    if attempt < 2:
                        time.sleep(5)
                    continue
                page_data = resp.json()
                if page_data:
                    break
                last_error = 'empty response'
            except (Exception,) as e:
                last_error = str(e)
            if attempt < 2:
                time.sleep(5)

        if not page_data or not page_data.get('success'):
            msg = f'last error: {last_error}' if last_error else 'inventory may be private'
            send_message(f'❌ Failed after 3 attempts ({msg}).')
            return

        all_assets.extend(page_data.get('assets', []))
        all_descriptions.extend(page_data.get('descriptions', []))

        if page_data.get('more_items') and page_data.get('last_assetid'):
            start_assetid = page_data['last_assetid']
            time.sleep(1)
        else:
            break

    desc_map = {}
    for d in all_descriptions:
        if d.get('marketable') == 1:
            desc_map[d['classid']] = d['market_hash_name']

    counts: dict = {}
    for asset in all_assets:
        name = desc_map.get(asset.get('classid'))
        if name:
            counts[name] = counts.get(name, 0) + int(asset.get('amount', 1))

    if not counts:
        send_message('📭 No marketable CS2 items found in inventory.')
        return

    added = updated = 0
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.cursor()
        for name, qty in counts.items():
            try:
                cur.execute('INSERT INTO watchlist (name, qty, added_at) VALUES (?, ?, ?)',
                            (name, qty, now))
                added += 1
            except sqlite3.IntegrityError:
                cur.execute('UPDATE watchlist SET qty = ? WHERE name = ?', (qty, name))
                updated += 1
        conn.commit()

    lines = [f'✅ Scan complete: {added} added, {updated} updated\n']
    for name, qty in sorted(counts.items()):
        lines.append(f'• {qty}× {name}')

    chunk = ''
    for line in lines:
        if len(chunk) + len(line) + 1 > 4000:
            send_message(chunk)
            chunk = ''
        chunk += line + '\n'
    if chunk:
        send_message(chunk)


def handle_refresh():
    send_message('🔄 Starting price update...')
    daily_update()


def handle_report():
    send_message('📋 Generating full report...')
    daily_update()
    result = generate_chart()
    if result is None:
        pass
    elif result:
        send_photo(result, '📊 Portfolio Chart')


def handle_rates():
    rates = get_exchange_rates()

    uah = rates['uah_per_usd']
    market_eur = rates['market_eur_per_usd']
    chain_eur = rates.get('chain_eur_per_usd')
    source = rates['source']

    usd_to_uah = f'₴{uah:.2f}'
    usd_to_eur_market = f'€{market_eur:.4f}'

    lines = [
        '💱 <b>Exchange Rates</b>',
        f'🕐 {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC',
        f'📡 Source: {source}',
        '',
        f'<b>1 USD → UAH:</b> {usd_to_uah}',
        f'<b>1 USD → EUR:</b> {usd_to_eur_market} (market / er-api)',
    ]

    if chain_eur:
        uah_per_eur = rates.get('uah_per_eur')
        spread = (chain_eur - market_eur) / market_eur * 100
        spread_emoji = '🟢' if spread >= -1.5 else ('🟡' if spread >= -3.0 else '🔴')
        lines.append(f'<b>1 USD → EUR:</b> €{chain_eur:.4f} (UAH chain) {spread_emoji} {spread:+.2f}% vs market')
        if uah_per_eur:
            lines.append(f'<b>1 EUR → UAH:</b> ₴{uah_per_eur:.2f}')

    lines += [
        '',
        '💡 UAH chain = convert USD→UAH→EUR via mono sell rates',
        '   (realistic Ukrainian cash-out path)',
    ]

    send_message('\n'.join(lines))
