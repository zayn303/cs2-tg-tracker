import time
import requests
from typing import Optional, Tuple
from .config import STEAM_PRICE_URL, DELAY, session

# 429 backoff schedule (seconds): 60, 120, 180
# Steam's cooldown after rate-limit is 60-120s; starting at 20s just burns retries.
_429_WAITS = [60, 120, 180]


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
    except Exception:
        pass
    return None


def _parse_price(price_str: Optional[str]) -> Optional[float]:
    if not price_str:
        return None
    try:
        return float(price_str.replace('$', '').replace(',', '').strip())
    except ValueError:
        return None


def get_current_price(market_hash_name: str, max_retries: int = 3) -> Tuple[Optional[float], bool]:
    """
    Returns (price_usd, was_rate_limited).
    price_usd is None if all retries failed.
    was_rate_limited is True if a 429 was encountered this call.
    Tries lowest_price first, falls back to median_price (needed for sub-$0.10 items).
    """
    params = {
        'appid': 730,
        'currency': 1,
        'market_hash_name': market_hash_name
    }
    rate_limited = False

    for attempt in range(max_retries):
        try:
            resp = session.get(STEAM_PRICE_URL, params=params, timeout=15)

            if resp.status_code == 429:
                rate_limited = True
                wait = _429_WAITS[min(attempt, len(_429_WAITS) - 1)]
                print(f'⏳ Rate limited (attempt {attempt + 1}), waiting {wait}s')
                time.sleep(wait)
                continue

            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    price = _parse_price(data.get('lowest_price'))
                    if price is None:
                        price = _parse_price(data.get('median_price'))
                    if price is not None:
                        return price, rate_limited
                # success=False or no price field at all
                return None, rate_limited

            # Non-200, non-429: treat as transient error
            print(f'⚠️ Steam returned HTTP {resp.status_code} for {market_hash_name}')
            if attempt < max_retries - 1:
                time.sleep(DELAY)

        except (requests.RequestException, ValueError) as e:
            print(f'⚠️ Error fetching price: {e}')
            if attempt < max_retries - 1:
                time.sleep(DELAY)

    return None, rate_limited
