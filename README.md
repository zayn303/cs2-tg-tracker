# Steam Market Price Tracker

A Telegram bot that watches your CS2 inventory and Steam market items — tracking prices in UAH, USD, and EUR with daily reports and interactive charts.

---

## What it does

You send it Steam market links, it tracks the prices. Every morning at 9:00 UTC you get a report showing how your portfolio changed over the last 24h, 7 days, and 30 days. You can also ask for updates anytime with a button tap.

---

## Before you start

You'll need two things:

**1. A bot token** — message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the steps, and copy the token it gives you.

**2. Your chat ID** — message [@userinfobot](https://t.me/userinfobot) and it'll tell you your numeric ID.

---

## Setup

```bash
# Clone the repo and enter it
git clone https://github.com/your-username/tg-cs-tracker.git
cd tg-cs-tracker

# Copy the config template and fill it in
cp .env.example .env
nano .env
```

Your `.env` should look like this:

```
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_CHAT_ID=your_numeric_chat_id
```

Then just run it:

```bash
chmod +x start.sh
./start.sh
```

First launch takes ~30 seconds to create a virtual environment and install packages. After that it starts instantly.

---

## Running in the background

Use `screen` so the bot keeps running after you close the terminal:

```bash
screen -S tgbot
./start.sh
# To detach: Ctrl+A, then D
```

To check on it later: `screen -r tgbot`

To stop it: reattach and press `Ctrl+C`

---

## Bot commands

| Command | What it does |
|---|---|
| `/start` | Show help |
| `/add <url> [qty]` | Add a Steam market item to your watchlist |
| `/list` | Show your watchlist with action buttons |
| `/chart` | Generate a price history chart |
| `/remove <name>` | Remove an item (partial name works) |
| `/refresh` | Fetch current prices right now |

### Adding items

Copy the URL from the Steam market listing page and paste it after `/add`:

```
/add https://steamcommunity.com/market/listings/730/AK-47%20%7C%20Redline%20%28Field-Tested%29
```

To track multiple copies, add a number at the end:

```
/add https://steamcommunity.com/market/listings/730/Dreams%20%26%20Nightmares%20Case 10
```

### Removing items

You don't need the full name — a fragment works:

```
/remove AK-47
/remove Dreams
```

---

## Interactive buttons

After `/list` you'll see buttons to:

- **📊 Show Chart** — price history graph (needs at least 2 days of data)
- **🔄 Refresh** — pull current prices immediately
- **💱 UAH / USD / EUR** — switch your preferred display currency

The chart will use whichever currency you've selected.

---

## Importing your CS2 inventory

If you want to bulk-add everything from your Steam inventory, use the included helper script:

```bash
python discover_inv.py YOUR_STEAM_ID_64
```

It prints ready-to-paste `/add` commands for every item in your public inventory. Your Steam inventory must be set to **Public** in privacy settings for this to work.

To find your Steam ID: go to your profile URL or use [steamid.io](https://steamid.io).

---

## Daily reports

Sent automatically at **09:00 UTC** and include:

- Total portfolio value in UAH, USD, and EUR
- Change compared to 24h / 7 days / 30 days ago
- Item-by-item breakdown sorted by value
- Live exchange rate source (Monobank / NBU)

---

## Project files

```
├── tg_bot.py         — the bot itself
├── discover_inv.py   — bulk import from your Steam inventory
├── start.sh          — startup script (handles venv + install)
├── requirements.txt  — Python dependencies
├── .env.example      — config template
└── CLAUDE.md         — dev notes
```

Files created automatically (not in the repo):

```
├── venv/             — Python virtual environment
├── inventory.db      — your watchlist and price history
└── plots/            — saved chart images
```

---

## Troubleshooting

**Bot isn't responding**
```bash
screen -r tgbot   # check if it's still running
ps aux | grep tg_bot
```

**Chart says "not enough data"**
Charts need at least 2 days of recorded prices. Use `/refresh` today and again tomorrow — then `/chart` will work.

**matplotlib won't install**
Remove it from `requirements.txt` and restart. The bot works fine without charts.

**Inventory import fails with 403**
Your Steam inventory is set to Private. Go to Steam → Edit Profile → Privacy Settings → set Game details to **Public**.

---

## License

MIT