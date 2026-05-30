from typing import Dict
from .config import session


def get_exchange_rates() -> Dict[str, float]:
    uah_rate = None
    uah_per_eur = None
    source = 'fallback'

    try:
        resp = session.get('https://api.monobank.ua/bank/currency', timeout=10)
        resp.raise_for_status()
        for rate in resp.json():
            codeA = rate.get('currencyCodeA')
            codeB = rate.get('currencyCodeB')
            if codeA == 840 and codeB == 980:
                uah_rate = rate.get('rateSell')
                source = 'monobank'
            elif codeA == 978 and codeB == 980:
                uah_per_eur = rate.get('rateSell')
    except (Exception,):
        pass

    if uah_rate is None:
        try:
            resp = session.get('https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json', timeout=10)
            resp.raise_for_status()
            for rate in resp.json():
                if rate.get('cc') == 'USD':
                    uah_rate = rate.get('rate')
                    source = 'nbu'
                    break
        except (Exception,):
            pass

    if uah_rate is None:
        uah_rate = 41.5
        source = 'fallback'

    chain_eur_per_usd = None
    if uah_rate and uah_per_eur and uah_per_eur > 0:
        chain_eur_per_usd = uah_rate / uah_per_eur

    market_eur_per_usd = 0.92
    try:
        resp = session.get('https://open.er-api.com/v6/latest/USD', timeout=10)
        resp.raise_for_status()
        market_eur_per_usd = resp.json().get('rates', {}).get('EUR', 0.92)
    except (Exception,):
        pass

    eur_rate = chain_eur_per_usd if chain_eur_per_usd else market_eur_per_usd

    return {
        'uah_per_usd': uah_rate,
        'uah_per_eur': uah_per_eur,
        'eur_per_usd': eur_rate,
        'chain_eur_per_usd': chain_eur_per_usd,
        'market_eur_per_usd': market_eur_per_usd,
        'source': source
    }
