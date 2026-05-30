import time
import requests
from typing import Optional
from .config import STEAM_PRICE_URL, DELAY, session


def check_steam_up() -> bool:
    try:
        resp = session.get(
            'https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/',
            timeout=5
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def resolve_steam_id(input_str: str) -> Optional[str]:
    input_str = input_str.strip()
    if input_str.isdigit() and len(input_str) == 17:
        return input_str
    if 'steamcommunity.com/id/' in input_str:
        input_str = input_str.rstrip('/').split('/id/')[-1].split('/')[0].split('#')[0]
    try:
        resp = session.get(
            f'https://steamcommunity.com/id/{input_str}?xml=1',
            timeout=10
        )
        resp.raise_for_status()
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        steamid = root.findtext('steamID64')
        if steamid and steamid.isdigit():
            return steamid
    except (requests.RequestException, ValueError) as e:
        pass
    except Exception:
        pass
    return None


def get_current_price(market_hash_name: str, max_retries: int = 3) -> Optional[float]:
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
