#!/usr/bin/env python3
"""
CS2 Inventory Exporter
Outputs your inventory as /add <market_url> <quantity> lines
Usage: python inventory_export.py <STEAM_ID_64>
"""

import sys
import time
import urllib.parse
import requests
from collections import Counter

def fetch_inventory(steam_id: str) -> list:
    items = []
    start = 0

    while True:
        url = (
            f"https://steamcommunity.com/inventory/{steam_id}/730/2"
            f"?l=english&count=2000&start_assetid={start}"
        )
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        except requests.RequestException as e:
            print(f"❌ Network error: {e}", file=sys.stderr)
            sys.exit(1)

        if resp.status_code == 403:
            print("❌ Inventory is private. Set it to Public in Steam privacy settings.", file=sys.stderr)
            sys.exit(1)
        if resp.status_code == 429:
            print("⚠️ Rate limited, waiting 10s...", file=sys.stderr)
            time.sleep(10)
            continue
        if not resp.ok:
            print(f"❌ Steam returned HTTP {resp.status_code}", file=sys.stderr)
            sys.exit(1)

        data = resp.json()

        if not data.get("success"):
            print("❌ Steam returned success=false. Inventory may be private or empty.", file=sys.stderr)
            sys.exit(1)

        assets = data.get("assets", [])
        descriptions = {
            (d["classid"], d["instanceid"]): d
            for d in data.get("descriptions", [])
        }

        for asset in assets:
            key = (asset["classid"], asset["instanceid"])
            desc = descriptions.get(key, {})
            name = desc.get("market_hash_name")
            marketable = desc.get("marketable", 0)
            if name and marketable:
                items.append(name)

        more = data.get("more_items", 0)
        if not more:
            break

        # next page start
        start = data.get("last_assetid", 0)
        time.sleep(1.5)  # be polite to Steam

    return items


def main():
    if len(sys.argv) < 2:
        print("Usage: python inventory_export.py <STEAM_ID_64>")
        print("Example: python inventory_export.py 76561198012345678")
        sys.exit(1)

    steam_id = sys.argv[1].strip()
    print(f"⏳ Fetching CS2 inventory for {steam_id}...", file=sys.stderr)

    items = fetch_inventory(steam_id)

    if not items:
        print("⚠️ No marketable items found.", file=sys.stderr)
        sys.exit(0)

    counts = Counter(items)
    base_url = "https://steamcommunity.com/market/listings/730/"

    print(f"✅ Found {len(counts)} unique items ({sum(counts.values())} total)\n", file=sys.stderr)

    for name, qty in sorted(counts.items()):
        encoded = urllib.parse.quote(name, safe="")
        print(f"/add {base_url}{encoded} {qty}")


if __name__ == "__main__":
    main()