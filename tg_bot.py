#!/usr/bin/env python3
"""
Telegram Market Price Tracker - Optimized
Resource-efficient version with minimal memory/CPU/network footprint
"""

import sqlite3
import requests
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from contextlib import contextmanager
import threading
import schedule
import os
from dotenv import load_dotenv

# Try to import matplotlib (optional for charts)
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print('⚠️ matplotlib not available - chart feature disabled')

load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
DB_PATH = 'inventory.db'
DELAY = 2.5
STEAM_PRICE_URL = 'https://steamcommunity.com/market/priceoverview/'
CHARTS_DIR = 'plots'
MAX_MESSAGE_LENGTH = 3900  # Leave headroom under 4000 char limit

# Global HTTP session for connection reuse
session = requests.Session()
session.headers.update({'Connection': 'keep-alive'})


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize SQLite database with indexes."""
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                total_uah REAL,
                total_usd REAL,
                total_eur REAL,
                item_count INTEGER
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS item_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                name TEXT,
                qty INTEGER,
                price_uah REAL,
                price_usd REAL,
                price_eur REAL,
                UNIQUE(date, name)
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                qty INTEGER DEFAULT 1,
                added_at TEXT
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Create indexes for faster queries
        cur.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_item_prices_date ON item_prices(date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_item_prices_name ON item_prices(name)')

        # Set default currency
        cur.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                   ('preferred_currency', 'UAH'))

        conn.commit()


def get_exchange_rates() -> Dict[str, float]:
    """Fetch exchange rates (UAH primary) with timeout and error handling."""
    uah_rate = None
    source = 'fallback'

    # Try monobank
    try:
        resp = session.get('https://api.monobank.ua/bank/currency', timeout=10)
        resp.raise_for_status()
        for rate in resp.json():
            if rate.get('currencyCodeA') == 840 and rate.get('currencyCodeB') == 980:
                uah_rate = rate.get('rateSell')
                source = 'monobank'
                break
    except (requests.RequestException, ValueError, KeyError):
        pass

    # Fallback to NBU
    if uah_rate is None:
        try:
            resp = session.get('https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json', timeout=10)
            resp.raise_for_status()
            for rate in resp.json():
                if rate.get('cc') == 'USD':
                    uah_rate = rate.get('rate')
                    source = 'nbu'
                    break
        except (requests.RequestException, ValueError, KeyError):
            pass

    if uah_rate is None:
        uah_rate = 41.5
        source = 'fallback'

    # EUR/USD
    eur_rate = 0.92
    try:
        resp = session.get('https://open.er-api.com/v6/latest/USD', timeout=10)
        resp.raise_for_status()
        eur_rate = resp.json().get('rates', {}).get('EUR', 0.92)
    except (requests.RequestException, ValueError, KeyError):
        pass

    return {
        'uah_per_usd': uah_rate,
        'eur_per_usd': eur_rate,
        'source': source
    }


def get_current_price(market_hash_name: str, max_retries: int = 3) -> Optional[float]:
    """Fetch USD price from Steam Market with exponential backoff."""
    params = {
        'appid': 730,
        'currency': 1,
        'market_hash_name': market_hash_name
    }

    for attempt in range(max_retries):
        try:
            resp = session.get(STEAM_PRICE_URL, params=params, timeout=15)

            if resp.status_code == 429:
                wait_time = 20 * (2 ** attempt)
                print(f'⏳ Rate limited, waiting {wait_time}s')
                time.sleep(wait_time)
                continue

            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    price_str = data.get('lowest_price', '').replace('$', '').replace(',', '')
                    if price_str:
                        return float(price_str)

            return None

        except (requests.RequestException, ValueError) as e:
            print(f'⚠️ Error fetching price: {e}')
            if attempt < max_retries - 1:
                time.sleep(DELAY)

    return None


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
    """Split long messages into chunks under max_length."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    lines = text.split('\n')
    current_chunk = ''

    for line in lines:
        if len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk += line + '\n'
        else:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
            current_chunk = line + '\n'

    if current_chunk:
        chunks.append(current_chunk.rstrip())

    return chunks


def send_message(text: str, reply_markup=None):
    """Send Telegram message with automatic splitting for long messages."""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    chunks = split_message(text)

    for i, chunk in enumerate(chunks):
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': chunk,
            'parse_mode': 'HTML'
        }
        # Only add reply_markup to last chunk
        if reply_markup and i == len(chunks) - 1:
            data['reply_markup'] = reply_markup

        try:
            session.post(url, json=data, timeout=15)
        except requests.RequestException as e:
            print(f'⚠️ Error sending message: {e}')


def send_photo(photo_path: str, caption: str = ''):
    """Send photo to Telegram."""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'
    try:
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
            session.post(url, data=data, files=files, timeout=30)
    except (requests.RequestException, IOError) as e:
        print(f'⚠️ Error sending photo: {e}')


def get_preferred_currency(conn=None) -> str:
    """Get user's preferred currency. Reuses connection if provided."""
    if conn:
        cur = conn.cursor()
        cur.execute('SELECT value FROM settings WHERE key = ?', ('preferred_currency',))
        row = cur.fetchone()
        return row[0] if row else 'UAH'

    with get_db() as conn:
        return get_preferred_currency(conn)


def set_preferred_currency(currency: str):
    """Set user's preferred currency."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                   ('preferred_currency', currency))
        conn.commit()


def generate_chart():
    """Generate price history chart for preferred currency (memory efficient)."""
    if not MATPLOTLIB_AVAILABLE:
        return None

    with get_db() as conn:
        pref_currency = get_preferred_currency(conn)

        # Get historical data (only needed columns)
        cur = conn.cursor()
        cur.execute('SELECT date, total_uah, total_usd, total_eur FROM snapshots ORDER BY date')
        rows = cur.fetchall()

        if not rows or len(rows) < 2:
            return False

    # Currency configuration
    currency_config = {
        'UAH': {'idx': 1, 'color': '#34d399', 'symbol': '₴', 'name': 'UAH'},
        'USD': {'idx': 2, 'color': '#00d4ff', 'symbol': '$', 'name': 'USD'},
        'EUR': {'idx': 3, 'color': '#a78bfa', 'symbol': '€', 'name': 'EUR'}
    }

    config = currency_config.get(pref_currency, currency_config['UAH'])

    # Parse dates and extract values in one pass
    dates = [datetime.strptime(row[0], '%Y-%m-%d') for row in rows]
    values = [row[config['idx']] for row in rows]

    # Create chart
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor('#0f0f1a')
    ax.set_facecolor('#0f0f1a')

    # Plot
    ax.plot(dates, values, color=config['color'], linewidth=3, marker='o', markersize=8,
            markerfacecolor=config['color'], markeredgecolor='white', markeredgewidth=1.5)

    # Labels
    ax.set_title(f"Portfolio Value History ({config['name']})",
                fontsize=16, fontweight='bold', color=config['color'], pad=20)
    ax.set_ylabel(f"Value ({config['name']})", color=config['color'], fontsize=14, fontweight='bold')
    ax.set_xlabel('Date', color='white', fontsize=12)
    ax.grid(alpha=0.3, linestyle='--', linewidth=0.5)
    ax.tick_params(axis='y', labelcolor=config['color'], labelsize=11)
    ax.tick_params(axis='x', labelcolor='white', labelsize=10)

    # Annotate latest value
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

    # Calculate and show change
    if len(values) > 1:
        first_value = values[0]
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

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(dates)//10)))
    plt.xticks(rotation=45, ha='right')

    # Fill
    ax.fill_between(dates, values, alpha=0.2, color=config['color'])

    plt.tight_layout()
    os.makedirs(CHARTS_DIR, exist_ok=True)
    chart_path = os.path.join(CHARTS_DIR, datetime.now().strftime('%d.%m.%Y-%H:%M') + '.png')
    plt.savefig(chart_path, dpi=120, facecolor='#0f0f1a', edgecolor='none')
    plt.close(fig)  # Explicitly close to free memory

    return chart_path


def setup_bot_commands():
    """Set up bot command menu in Telegram."""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setMyCommands'
    commands = [
        {'command': 'start', 'description': '🏠 Show help'},
        {'command': 'add', 'description': '➕ Add item to watchlist'},
        {'command': 'list', 'description': '📋 Show watchlist'},
        {'command': 'remove', 'description': '🗑 Remove item'},
        {'command': 'chart', 'description': '📊 Show price chart'},
        {'command': 'refresh', 'description': '🔄 Update prices now'}
    ]

    try:
        resp = session.post(url, json={'commands': commands}, timeout=15)
        resp.raise_for_status()
        print('✅ Bot command menu set up')
    except requests.RequestException as e:
        print(f'⚠️ Error setting up commands: {e}')


def handle_add(text: str):
    """Add item to watchlist with optional quantity."""
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
    """Remove item from watchlist."""
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
    """Show watchlist with action buttons."""
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
                    {'text': '📊 Show Chart', 'callback_data': 'chart'},
                    {'text': '🔄 Refresh', 'callback_data': 'refresh'}
                ],
                [
                    {'text': '💱 UAH', 'callback_data': 'curr_UAH'},
                    {'text': '💱 USD', 'callback_data': 'curr_USD'},
                    {'text': '💱 EUR', 'callback_data': 'curr_EUR'}
                ]
            ]
        }
        send_message(msg, reply_markup=keyboard)
    else:
        send_message('📭 Watchlist is empty!\nUse /add &lt;url&gt; [qty] to track items.')


def handle_refresh():
    """Trigger immediate price update."""
    send_message('🔄 Starting price update...')
    daily_update()


def calculate_change(current: float, days_ago: int, date_today: str) -> Optional[float]:
    """Calculate percentage change efficiently."""
    with get_db() as conn:
        cur = conn.cursor()
        target_date = (datetime.strptime(date_today, '%Y-%m-%d') - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        cur.execute('SELECT total_uah FROM snapshots WHERE date = ? LIMIT 1', (target_date,))
        row = cur.fetchone()

    if row and row[0] and row[0] > 0:
        return ((current - row[0]) / row[0]) * 100
    return None


def format_change(change: Optional[float]) -> str:
    """Format % change with emoji."""
    if change is None:
        return '—'
    emoji = '🟢' if change >= 0 else '🔴'
    sign = '+' if change >= 0 else ''
    return f'{emoji} {sign}{change:.1f}%'


def daily_update():
    """Daily price update job (optimized)."""
    print(f'▶ Starting daily update at {datetime.now(timezone.utc).isoformat()}')

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT name, qty FROM watchlist')
        watchlist = cur.fetchall()

        if not watchlist:
            print('⚠️ Watchlist empty, skipping update')
            return

        print(f'📊 Fetching prices for {len(watchlist)} items')

        # Get exchange rates
        rates = get_exchange_rates()
        print(f"💱 Rates: 1 USD = ₴{rates['uah_per_usd']:.2f} ({rates['source']})")

        # Fetch prices
        item_data = []
        for i, (name, qty) in enumerate(watchlist, 1):
            print(f'[{i}/{len(watchlist)}] {qty}× {name}')
            price_usd = get_current_price(name) or 0.0

            item_data.append({
                'name': name,
                'qty': qty,
                'price_usd': price_usd,
                'price_uah': price_usd * rates['uah_per_usd'],
                'price_eur': price_usd * rates['eur_per_usd']
            })

            time.sleep(DELAY)

        # Calculate totals
        date_today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        total_uah = sum(item['price_uah'] * item['qty'] for item in item_data)
        total_usd = sum(item['price_usd'] * item['qty'] for item in item_data)
        total_eur = sum(item['price_eur'] * item['qty'] for item in item_data)
        total_items = sum(item['qty'] for item in item_data)

        # Save to DB
        cur.execute('''
            INSERT OR REPLACE INTO snapshots (date, total_uah, total_usd, total_eur, item_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (date_today, total_uah, total_usd, total_eur, total_items))

        for item in item_data:
            cur.execute('''
                INSERT OR REPLACE INTO item_prices (date, name, qty, price_uah, price_usd, price_eur)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (date_today, item['name'], item['qty'], item['price_uah'], item['price_usd'], item['price_eur']))

        conn.commit()

    # Calculate changes
    change_24h = calculate_change(total_uah, 1, date_today)
    change_7d = calculate_change(total_uah, 7, date_today)
    change_30d = calculate_change(total_uah, 30, date_today)

    # Build report (efficient string building)
    report_parts = [
        f'📊 <b>Market Report</b>',
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
        f'   7d: {format_change(change_7d)}',
        f'   30d: {format_change(change_30d)}',
        '',
        f"💱 Rates: 1 USD = ₴{rates['uah_per_usd']:.2f} ({rates['source']}) | €{rates['eur_per_usd']:.4f}",
        '',
        '🏷 <b>Items by total value</b>'
    ]

    # Add items sorted by total value
    sorted_items = sorted(item_data, key=lambda x: x['price_uah'] * x['qty'], reverse=True)

    for item in sorted_items:
        if item['price_usd'] > 0:
            unit_line = f"  ₴{item['price_uah']:.2f} / ${item['price_usd']:.2f} / €{item['price_eur']:.2f}"

            if item['qty'] > 1:
                total_uah_item = item['price_uah'] * item['qty']
                total_usd_item = item['price_usd'] * item['qty']
                total_eur_item = item['price_eur'] * item['qty']
                report_parts.extend([
                    '',
                    f"• {item['qty']}× {item['name']}",
                    f"{unit_line} ea.",
                    f"  = ₴{total_uah_item:,.2f} / ${total_usd_item:,.2f} / €{total_eur_item:,.2f}"
                ])
            else:
                report_parts.extend([
                    '',
                    f"• {item['name']}",
                    unit_line
                ])

    report = '\n'.join(report_parts)

    # Add action buttons
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '📊 Show Chart', 'callback_data': 'chart'},
                {'text': '📋 View List', 'callback_data': 'list_cmd'}
            ]
        ]
    }

    send_message(report, reply_markup=keyboard)
    print('✅ Daily update complete')


def process_updates():
    """Long-polling for Telegram updates (optimized)."""
    print('🚀 Starting Telegram bot...')
    offset = 0

    while True:
        try:
            url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates'
            params = {'offset': offset, 'timeout': 30}

            resp = session.get(url, params=params, timeout=35)

            if resp.status_code != 200:
                print(f'⚠️ getUpdates failed: {resp.status_code}')
                time.sleep(5)
                continue

            data = resp.json()
            if not data.get('ok'):
                print(f'⚠️ getUpdates not ok')
                time.sleep(5)
                continue

            updates = data.get('result', [])

            for update in updates:
                offset = update['update_id'] + 1

                # Handle callback queries (button clicks)
                if 'callback_query' in update:
                    callback_query = update['callback_query']
                    callback_data = callback_query.get('data', '')
                    query_id = callback_query.get('id')

                    # Answer callback
                    session.post(
                        f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery',
                        json={'callback_query_id': query_id},
                        timeout=10
                    )

                    print(f'🔘 Button: {callback_data}')

                    if callback_data == 'chart':
                        result = generate_chart()
                        if result is None:
                            send_message('❌ Chart feature not available (matplotlib not installed)')
                        elif result:
                            send_photo(result, '📊 Price History Chart')
                        else:
                            send_message('❌ Not enough data to generate chart (need at least 2 days)')

                    elif callback_data == 'refresh':
                        handle_refresh()

                    elif callback_data == 'list_cmd':
                        handle_list()

                    elif callback_data.startswith('curr_'):
                        currency = callback_data.split('_')[1]
                        set_preferred_currency(currency)
                        send_message(f'✅ Preferred currency set to <b>{currency}</b>')

                    continue

                # Handle regular messages
                message = update.get('message', {})
                chat_id = str(message.get('chat', {}).get('id', ''))
                text = message.get('text', '')

                if chat_id != TELEGRAM_CHAT_ID:
                    continue

                print(f'💬 Command: {text}')

                # Handle commands
                if text.startswith('/add '):
                    handle_add(text[5:].strip())
                elif text.startswith('/remove '):
                    handle_remove(text[8:].strip())
                elif text == '/list':
                    handle_list()
                elif text == '/chart':
                    result = generate_chart()
                    if result is None:
                        send_message('❌ Chart feature not available (matplotlib not installed)')
                    elif result:
                        send_photo(result, '📊 Price History Chart')
                    else:
                        send_message('❌ Not enough data to generate chart (need at least 2 days)')
                elif text == '/refresh':
                    handle_refresh()
                elif text == '/start' or text == '/help':
                    help_msg = '''🤖 <b>Market Tracker Bot</b>

<b>Commands:</b>
/add &lt;url&gt; [qty] - Add item to watchlist
/remove &lt;name&gt; - Remove item
/list - Show watchlist with buttons
/chart - Show price history chart
/refresh - Update prices now

<b>Interactive Buttons:</b>
Use /list to see buttons for:
• 📊 Chart - View price history
• 🔄 Refresh - Update prices
• 💱 Currency - Set preferred currency (UAH/USD/EUR)

<b>Examples:</b>
/add https://steamcommunity.com/market/listings/730/AK-47%20%7C%20Redline%20%28Field-Tested%29
/add https://steamcommunity.com/market/listings/730/Dreams%20%26%20Nightmares%20Case 10
/remove Dreams

Daily reports sent automatically at 09:00 UTC.'''
                    reply_keyboard = {
                        'keyboard': [
                            [{'text': '/list'}, {'text': '/chart'}],
                            [{'text': '/refresh'}, {'text': '/add'}]
                        ],
                        'resize_keyboard': True,
                        'persistent': True
                    }
                    send_message(help_msg, reply_markup=reply_keyboard)

        except requests.RequestException as e:
            print(f'⚠️ Network error in bot loop: {e}')
            time.sleep(5)
        except Exception as e:
            print(f'⚠️ Error in bot loop: {e}')
            time.sleep(5)


def run_scheduler():
    """Run scheduled jobs in background thread."""
    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    """Main entry point."""
    print('🤖 Telegram bot starting...')

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print('❌ ERROR: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables')
        return

    # Initialize
    init_db()
    setup_bot_commands()

    # Schedule daily update
    schedule.every().day.at('09:00').do(daily_update)

    # Start scheduler in background
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    print('✅ Bot ready! Daily updates at 09:00 UTC')

    # Start polling
    process_updates()


if __name__ == '__main__':
    main()