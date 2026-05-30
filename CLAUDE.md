# CS2 Inventory Tracker — Telegram Bot

## What This Is

Telegram bot that tracks CS2 (Counter-Strike 2) inventory items listed on Steam Community Market. Fetches daily prices, persists to SQLite, generates portfolio value charts, and sends reports to a private Telegram chat.

## Architecture

Single file: `tg_bot.py`. No framework — raw `requests` for both Steam API and Telegram Bot API (long-polling).

**Stack:** Python 3, SQLite (`inventory.db`), `schedule` for cron, `matplotlib` for charts, `requests` for HTTP.

**Run:** `./start.sh` (creates venv, installs deps, runs bot).

## DB Schema (`inventory.db`)

| Table | Purpose |
|---|---|
| `snapshots` | One row per price-fetch run. `date` (datetime string), `total_uah/usd/eur`, `item_count` |
| `item_prices` | Per-item price at each snapshot. `(date, name)` unique. |
| `watchlist` | Items being tracked. `name` = Steam market hash name, `qty` |
| `settings` | KV store. Keys: `preferred_currency`, `last_item_data` (JSON cache) |

## Data Flow

1. Scheduler fires `daily_update()` at 09:00 UTC (startup: `schedule.every().day.at('09:00')`)
2. Fetches UAH rate from Monobank → NBU fallback → hardcoded 41.5 fallback
3. Fetches USD price per item from `steamcommunity.com/market/priceoverview/` (2.5s delay between items to avoid 429)
4. Inserts snapshot row with full datetime key (multiple refreshes per day each get their own row)
5. Sends summary message to Telegram with inline buttons

## Known Issue: Zero-Value Gaps in Chart

**Root cause:** When network is unreachable during a scheduled update, `get_current_price()` returns `None` → falls back to `0.0` → snapshot saved with all-zero totals → graph shows cliff-drop to 0.

**Pattern:** Happens at scheduled run time (~07:05 UTC based on DB). Not caught at save time.

**Fix needed (not yet implemented):** In `daily_update()`, before `conn.commit()`, check if `total_usd == 0` and all item prices are 0 — if so, skip the insert (network failure, not real data). Could also check if `get_exchange_rates()` returned `source='fallback'` AND all prices are 0.

**Cleanup script:** `null_deleteion.py` — interactive script to delete zero/null snapshot rows and their orphaned `item_prices` rows. Run manually: `python3 null_deleteion.py`.

## Bot Commands

| Command | Action |
|---|---|
| `/add <steam_url> [qty]` | Add item to watchlist |
| `/remove <fragment>` | Remove item by partial name match |
| `/list` | Show watchlist + inline buttons (chart, refresh, currency) |
| `/chart` | Generate and send PNG chart (matplotlib) |
| `/refresh` | Trigger immediate price update |

## Chart Generation (`generate_chart()`)

- Reads all `snapshots` rows ordered by date
- Plots portfolio value in preferred currency (UAH/USD/EUR)
- Y-axis zoomed to data range (25% padding), NOT from 0 — this makes zero-value rows look like catastrophic drops
- Saves PNG to `plots/` dir with timestamp filename
- Shows % change from first to last data point in top-left corner

## Exchange Rates

- UAH: Monobank API → NBU API → 41.5 hardcoded fallback
- EUR: open.er-api.com → 0.92 hardcoded fallback
- Rates fetched fresh on every `daily_update()` call

## Config (`.env`)

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Files

```
tg_bot.py          — main bot (everything)
null_deleteion.py  — one-shot DB cleanup for zero/null snapshots
inventory.db       — SQLite database
plots/             — generated chart PNGs
start.sh           — venv setup + launch script
requirements.txt   — requests, schedule, python-dotenv, matplotlib
```
