import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
DB_PATH = 'inventory.db'
DELAY = 3.5
STEAM_PRICE_URL = 'https://steamcommunity.com/market/priceoverview/'
CHARTS_DIR = 'plots'
MAX_MESSAGE_LENGTH = 3900

session = requests.Session()
session.headers.update({'Connection': 'keep-alive'})
