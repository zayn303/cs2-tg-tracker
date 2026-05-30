import time
import json
import traceback
import requests
import schedule
import threading
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, session
from .db import init_db, get_db, set_preferred_currency
from .telegram import send_message, send_photo, setup_bot_commands
from .charts import generate_chart, MATPLOTLIB_AVAILABLE
from .reports import build_items_report
from .handlers import handle_add, handle_remove, handle_list, handle_scan, handle_refresh, handle_report, handle_rates
from .scheduler import daily_update, run_scheduler


def process_updates():
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
                print('⚠️ getUpdates not ok')
                time.sleep(5)
                continue

            for update in data.get('result', []):
                offset = update['update_id'] + 1

                if 'callback_query' in update:
                    callback_query = update['callback_query']
                    callback_data = callback_query.get('data', '')
                    query_id = callback_query.get('id')

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

                    elif callback_data == 'report':
                        handle_report()

                    elif callback_data == 'rates':
                        handle_rates()

                    elif callback_data == 'list_cmd':
                        handle_list()

                    elif callback_data == 'items_detail':
                        with get_db() as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT value FROM settings WHERE key = 'last_item_data'")
                            row = cur.fetchone()
                        if row:
                            cached = json.loads(row[0])
                            report = build_items_report(cached['items'], cached['date'])
                            send_message(report)
                        else:
                            send_message('❌ No item data cached yet. Try /refresh first.')

                    elif callback_data.startswith('curr_'):
                        currency = callback_data.split('_')[1]
                        set_preferred_currency(currency)
                        send_message(f'✅ Preferred currency set to <b>{currency}</b>')

                    continue

                message = update.get('message', {})
                chat_id = str(message.get('chat', {}).get('id', ''))
                text = message.get('text', '')

                if chat_id != TELEGRAM_CHAT_ID:
                    continue

                print(f'💬 Command: {text}')

                if text.startswith('/scan ') or text == '/scan':
                    handle_scan(text[6:].strip() if text.startswith('/scan ') else '')
                elif text.startswith('/add '):
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
                elif text == '/report':
                    handle_report()
                elif text == '/rates':
                    handle_rates()
                elif text in ('/start', '/help'):
                    help_msg = '''🤖 <b>Market Tracker Bot</b>

<b>Commands:</b>
/report - Full report + chart on demand
/rates - Current exchange rates (USD/UAH/EUR)
/scan &lt;steamid64&gt; - Import inventory from Steam
/add &lt;url&gt; [qty] - Add item to watchlist
/remove &lt;name&gt; - Remove item
/list - Show watchlist with buttons
/chart - Show price history chart
/refresh - Update prices (no chart)

<b>Interactive Buttons:</b>
Use /list to see buttons for:
• 📋 Report - Full report + chart
• 📊 Chart - View price history only
• 🔄 Refresh - Update prices only
• 💱 Rates - Live exchange rates
• 💱 Currency - Set preferred currency (UAH/USD/EUR)

<b>Examples:</b>
/add https://steamcommunity.com/market/listings/730/AK-47%20%7C%20Redline%20%28Field-Tested%29
/add https://steamcommunity.com/market/listings/730/Dreams%20%26%20Nightmares%20Case 10
/remove Dreams

Daily reports sent automatically at 09:00 UTC.'''
                    reply_keyboard = {
                        'keyboard': [
                            [{'text': '/report'}, {'text': '/chart'}, {'text': '/rates'}],
                            [{'text': '/list'}, {'text': '/refresh'}, {'text': '/add'}]
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
            traceback.print_exc()
            time.sleep(5)


def main():
    print('🤖 Telegram bot starting...')

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print('❌ ERROR: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables')
        return

    init_db()
    setup_bot_commands()

    schedule.every().day.at('09:00').do(daily_update)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    print('✅ Bot ready! Daily updates at 09:00 UTC')
    process_updates()
