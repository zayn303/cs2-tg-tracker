#!/usr/bin/env python3
"""
Standalone DB cleanup script.
Deletes snapshot rows where all values are null or zero.
Run once manually: python cleanup_db.py
"""

import sqlite3

DB_PATH = 'inventory.db'


def cleanup():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Show before state
    cur.execute('SELECT COUNT(*) FROM snapshots')
    total_before = cur.fetchone()[0]

    cur.execute('''
        SELECT date, total_uah, total_usd, total_eur
        FROM snapshots
        WHERE (total_uah IS NULL OR total_uah = 0)
          AND (total_usd IS NULL OR total_usd = 0)
          AND (total_eur IS NULL OR total_eur = 0)
    ''')
    bad_rows = cur.fetchall()

    if not bad_rows:
        print('✅ No null/zero snapshots found. DB is clean.')
        conn.close()
        return

    print(f'🔍 Found {len(bad_rows)} null/zero snapshot(s) to delete:')
    for row in bad_rows:
        print(f'   date={row[0]}  UAH={row[1]}  USD={row[2]}  EUR={row[3]}')

    confirm = input(f'\n⚠️  Delete {len(bad_rows)} row(s)? [y/N]: ').strip().lower()
    if confirm != 'y':
        print('❌ Aborted.')
        conn.close()
        return

    # Delete bad snapshots
    cur.execute('''
        DELETE FROM snapshots
        WHERE (total_uah IS NULL OR total_uah = 0)
          AND (total_usd IS NULL OR total_usd = 0)
          AND (total_eur IS NULL OR total_eur = 0)
    ''')

    # Also delete orphaned item_prices for those dates
    bad_dates = [row[0] for row in bad_rows]
    cur.executemany('DELETE FROM item_prices WHERE date = ?', [(d,) for d in bad_dates])

    conn.commit()

    cur.execute('SELECT COUNT(*) FROM snapshots')
    total_after = cur.fetchone()[0]

    print(f'\n✅ Done. Snapshots: {total_before} → {total_after} (deleted {total_before - total_after})')
    conn.close()


if __name__ == '__main__':
    cleanup()
