import sqlite3
from contextlib import contextmanager
from .config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
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

        cur.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_item_prices_date ON item_prices(date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_item_prices_name ON item_prices(name)')

        cur.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                    ('preferred_currency', 'UAH'))

        conn.commit()


def get_preferred_currency(conn=None) -> str:
    if conn:
        cur = conn.cursor()
        cur.execute('SELECT value FROM settings WHERE key = ?', ('preferred_currency',))
        row = cur.fetchone()
        return row[0] if row else 'UAH'

    with get_db() as conn:
        return get_preferred_currency(conn)


def set_preferred_currency(currency: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                    ('preferred_currency', currency))
        conn.commit()
