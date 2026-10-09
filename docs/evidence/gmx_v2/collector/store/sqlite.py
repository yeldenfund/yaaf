import json, sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "observatory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS traders (
    address TEXT PRIMARY KEY,
    subaccount INTEGER DEFAULT 0,
    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT
);
CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,
    ts TEXT DEFAULT CURRENT_TIMESTAMP,
    equity REAL, total_pnl REAL, pnl_window REAL,
    day_winrate REAL, avg_daily_pnl REAL,
    raw JSON
);
CREATE TABLE IF NOT EXISTS fills (
    address TEXT NOT NULL,
    t TEXT NOT NULL,
    market TEXT, side TEXT, liquidity TEXT, type TEXT,
    price REAL, size REAL, usd_notional REAL, fee REAL,
    position_side_before TEXT,
    position_size_before REAL,
    entry_price_before REAL,
    PRIMARY KEY (address, t, market, side, price, size)
);
CREATE TABLE IF NOT EXISTS yaaf_state (
    address TEXT PRIMARY KEY,
    ema REAL DEFAULT 300.0,
    round_history JSON DEFAULT '[]',
    total_trades INTEGER DEFAULT 0,
    last_s_raw REAL,
    last_sistema REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS yaaf_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,
    ts TEXT DEFAULT CURRENT_TIMESTAMP,
    s_raw REAL, sistema REAL, stage TEXT, profile TEXT,
    payload JSON
);
CREATE TABLE IF NOT EXISTS metrics (
    address TEXT NOT NULL,
    ts TEXT DEFAULT CURRENT_TIMESTAMP,
    payload JSON,
    PRIMARY KEY (address, ts)
);
"""


def conn():
    c = sqlite3.connect(DB_PATH)
    c.executescript(SCHEMA)
    return c


def upsert_trader(c, address, subaccount=0):
    c.execute(
        "INSERT INTO traders(address, subaccount, last_seen) VALUES (?,?,CURRENT_TIMESTAMP) "
        "ON CONFLICT(address) DO UPDATE SET last_seen=CURRENT_TIMESTAMP",
        (address, subaccount),
    )


def save_pnl_snapshot(c, address, stats):
    c.execute(
        "INSERT INTO pnl_snapshots(address, equity, total_pnl, pnl_window, day_winrate, avg_daily_pnl, raw) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            address,
            stats.get("equity_now"),
            stats.get("totalPnl_now"),
            stats.get("totalPnl_delta_window"),
            stats.get("day_winrate_pct"),
            stats.get("avg_daily_pnl"),
            json.dumps(stats),
        ),
    )


def save_fills(c, address, fills):
    rows = [
        (
            address,
            f["t"], f.get("market"), f.get("side"), f.get("liquidity"), f.get("type"),
            f.get("price"), f.get("size"), f.get("usd_notional"), f.get("fee"),
            f.get("positionSideBefore"), f.get("positionSizeBefore"), f.get("entryPriceBefore"),
        )
        for f in fills
    ]
    c.executemany(
        "INSERT OR IGNORE INTO fills(address,t,market,side,liquidity,type,price,size,"
        "usd_notional,fee,position_side_before,position_size_before,entry_price_before) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def save_metrics(c, address, metrics):
    c.execute(
        "INSERT OR REPLACE INTO metrics(address, payload) VALUES (?, ?)",
        (address, json.dumps(metrics)),
    )
