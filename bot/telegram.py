import requests
from typing import List, Optional
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MAX_MESSAGE_LENGTH, session


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
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
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    chunks = split_message(text)

    for i, chunk in enumerate(chunks):
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': chunk,
            'parse_mode': 'HTML'
        }
        if reply_markup and i == len(chunks) - 1:
            data['reply_markup'] = reply_markup

        try:
            session.post(url, json=data, timeout=15)
        except requests.RequestException as e:
            print(f'⚠️ Error sending message: {e}')


def send_photo(photo_path: str, caption: str = ''):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'
    try:
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
            session.post(url, data=data, files=files, timeout=30)
    except (requests.RequestException, IOError) as e:
        print(f'⚠️ Error sending photo: {e}')


def setup_bot_commands():
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setMyCommands'
    commands = [
        {'command': 'start',   'description': '🏠 Show help'},
        {'command': 'scan',    'description': '🔍 Import inventory from Steam'},
        {'command': 'add',     'description': '➕ Add item to watchlist'},
        {'command': 'list',    'description': '📋 Show watchlist'},
        {'command': 'remove',  'description': '🗑 Remove item'},
        {'command': 'report',  'description': '📋 Full report + chart on demand'},
        {'command': 'rates',   'description': '💱 Current exchange rates (USD/UAH/EUR)'},
        {'command': 'chart',   'description': '📊 Show price chart'},
        {'command': 'refresh', 'description': '🔄 Update prices now'}
    ]

    try:
        resp = session.post(url, json={'commands': commands}, timeout=15)
        resp.raise_for_status()
        print('✅ Bot command menu set up')
    except requests.RequestException as e:
        print(f'⚠️ Error setting up commands: {e}')
