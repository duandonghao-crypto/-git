"""
Database module — supports both PostgreSQL and SQLite.
Uses psycopg2 for PG, sqlite3 for SQLite.
All connections return dict-like rows.
"""
import os
import sqlite3
from contextlib import contextmanager

try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except ImportError:
    HAS_PG = False

from config import Config


def get_db():
    """Get database connection. Returns connection with dict-like rows.
    Uses DATABASE_URL if set (Render/Neon), otherwise local PG config."""
    if Config.DB_TYPE == "sqlite":
        conn = sqlite3.connect(getattr(Config, 'SQLITE_PATH', ':memory:'))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    else:
        if not HAS_PG:
            raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary")
        conn = psycopg2.connect(Config.db_url(), sslmode='require' if 'neon' in Config.db_url() else 'prefer')
    return conn


@contextmanager
def db_session():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def _pg_dict_cursor(conn):
    """Return a dict-like cursor for PG."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    """Initialize database schema (idempotent)."""
    if Config.DB_TYPE == "sqlite":
        _init_sqlite()
    else:
        _init_pg()


def _init_sqlite():
    with db_session() as conn:
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys=OFF")
        for stmt in _SCHEMA_SQLITE:
            c.execute(stmt)
        c.execute("PRAGMA foreign_keys=ON")
        conn.commit()


def _init_pg():
    if not HAS_PG:
        raise RuntimeError("psycopg2 not installed")
    conn = psycopg2.connect(Config.db_url(), sslmode='require' if 'neon' in Config.db_url() else 'prefer')
    conn.autocommit = True
    try:
        c = conn.cursor()
        for stmt in _SCHEMA_PG:
            try:
                c.execute(stmt)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    raise
    finally:
        conn.close()


_SCHEMA_SQLITE = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
    )""",
    """CREATE TABLE IF NOT EXISTS meters (
        meter_id TEXT NOT NULL, location TEXT DEFAULT '', usage_type TEXT DEFAULT '',
        ownership TEXT DEFAULT '', status TEXT DEFAULT 'active',
        user_id INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT (datetime('now','localtime')),
        updated_at TIMESTAMP DEFAULT (datetime('now','localtime')),
        PRIMARY KEY (meter_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meter_id TEXT NOT NULL, year_month TEXT NOT NULL,
        category TEXT NOT NULL CHECK(category IN ('电费支','电量支','电费收','电量收')),
        amount REAL DEFAULT 0, counterparty TEXT DEFAULT '',
        user_id INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_tx_meter ON transactions(meter_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_month ON transactions(year_month)",
    "CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id)",
    """CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        user_id INTEGER DEFAULT 1, UNIQUE(name, user_id),
        created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
    )""",
    """CREATE TABLE IF NOT EXISTS customer_meters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL, meter_id TEXT NOT NULL,
        valid_from TEXT DEFAULT '', valid_to TEXT DEFAULT NULL, note TEXT DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS receivables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meter_id TEXT NOT NULL, year_month TEXT NOT NULL,
        receivable_amount REAL DEFAULT 0, received_amount REAL DEFAULT 0,
        customer_name TEXT DEFAULT '',
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending','partial','paid')),
        confirmed_date TEXT DEFAULT '', received_date TEXT DEFAULT '', note TEXT DEFAULT '',
        user_id INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT (datetime('now','localtime')),
        updated_at TIMESTAMP DEFAULT (datetime('now','localtime'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_recv_user ON receivables(user_id)",
    """CREATE TABLE IF NOT EXISTS payment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receivable_id INTEGER NOT NULL, meter_id TEXT NOT NULL, year_month TEXT NOT NULL,
        amount REAL DEFAULT 0, payment_date TEXT DEFAULT '', customer_name TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
    )""",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL, table_name TEXT NOT NULL, detail TEXT DEFAULT '',
        user_id INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
    )""",
]

_SCHEMA_PG = [
    """CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, name VARCHAR(200) UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS meters (
        meter_id VARCHAR(50) NOT NULL, location VARCHAR(500) DEFAULT '',
        usage_type VARCHAR(200) DEFAULT '', ownership VARCHAR(500) DEFAULT '',
        status VARCHAR(20) DEFAULT 'active', user_id INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (meter_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY, meter_id VARCHAR(50) NOT NULL,
        year_month VARCHAR(10) NOT NULL,
        category VARCHAR(10) NOT NULL CHECK(category IN ('电费支','电量支','电费收','电量收')),
        amount DOUBLE PRECISION DEFAULT 0, counterparty VARCHAR(500) DEFAULT '',
        user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_tx_meter ON transactions(meter_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_month ON transactions(year_month)",
    "CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id)",
    """CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY, name VARCHAR(500) NOT NULL,
        user_id INTEGER DEFAULT 1, UNIQUE(name, user_id),
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS customer_meters (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER NOT NULL, meter_id VARCHAR(50) NOT NULL,
        valid_from VARCHAR(20) DEFAULT '', valid_to VARCHAR(20) DEFAULT NULL,
        note VARCHAR(500) DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS receivables (
        id SERIAL PRIMARY KEY, meter_id VARCHAR(50) NOT NULL,
        year_month VARCHAR(10) NOT NULL,
        receivable_amount DOUBLE PRECISION DEFAULT 0,
        received_amount DOUBLE PRECISION DEFAULT 0,
        customer_name VARCHAR(500) DEFAULT '',
        status VARCHAR(10) DEFAULT 'pending' CHECK(status IN ('pending','partial','paid')),
        confirmed_date VARCHAR(20) DEFAULT '', received_date VARCHAR(20) DEFAULT '',
        note VARCHAR(500) DEFAULT '', user_id INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_recv_user ON receivables(user_id)",
    """CREATE TABLE IF NOT EXISTS payment_history (
        id SERIAL PRIMARY KEY, receivable_id INTEGER NOT NULL,
        meter_id VARCHAR(50) NOT NULL, year_month VARCHAR(10) NOT NULL,
        amount DOUBLE PRECISION DEFAULT 0, payment_date VARCHAR(20) DEFAULT '',
        customer_name VARCHAR(500) DEFAULT '', created_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id SERIAL PRIMARY KEY, action VARCHAR(50) NOT NULL,
        table_name VARCHAR(50) NOT NULL, detail VARCHAR(1000) DEFAULT '',
        user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW()
    )""",
    # Seed default admin user with id=1
    "INSERT INTO users (id, name) VALUES (1, '管理员') ON CONFLICT (name) DO NOTHING",
]
