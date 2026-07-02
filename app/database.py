"""Database module - PostgreSQL (psycopg2) or SQLite."""
import os, sqlite3
from contextlib import contextmanager

try:
    import psycopg
    HAS_PG = True
    PG_V3 = True
    import psycopg.rows
except ImportError:
    try:
        import psycopg2
        import psycopg2.extras
        HAS_PG = True
        PG_V3 = False
    except ImportError:
        HAS_PG = False
        PG_V3 = False

from config import Config


class DBRow:
    """Dict row that also supports [0] index access using first value."""
    def __init__(self, d):
        self._d = d
        self._keys = list(d.keys()) if d else []
    def __getitem__(self, k):
        if isinstance(k, int):
            if 0 <= k < len(self._keys):
                return self._d[self._keys[k]]
            raise IndexError(k)
        return self._d[k]
    def keys(self): return self._d.keys()
    def values(self): return self._d.values()
    def items(self): return self._d.items()
    def get(self, k, d=None): return self._d.get(k, d)
    def __contains__(self, k): return k in self._d
    def __iter__(self): return iter(self._d)
    def __len__(self): return len(self._d)
    def __repr__(self): return repr(self._d)


def get_db():
    if Config.DB_TYPE == 'sqlite':
        conn = sqlite3.connect(getattr(Config, 'SQLITE_PATH', ':memory:'))
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        return conn
    if not HAS_PG:
        raise RuntimeError('psycopg not installed')
    if PG_V3:
        conn = psycopg.connect(Config.db_url(), row_factory=psycopg.rows.dict_row, prepare_threshold=None)
        # Wrap cursor to return DBRow
        _orig_cursor = conn.cursor
        def wrapped_cursor(*a, **kw):
            cur = _orig_cursor(*a, **kw)
            _orig_fetchone = cur.fetchone
            _orig_fetchall = cur.fetchall
            def new_fetchone():
                r = _orig_fetchone()
                return DBRow(r) if r else None
            def new_fetchall():
                return [DBRow(r) for r in _orig_fetchall()]
            cur.fetchone = new_fetchone
            cur.fetchall = new_fetchall
            return cur
        conn.cursor = wrapped_cursor
    else:
        conn = psycopg2.connect(Config.db_url())
    conn.autocommit = False
    return conn


@contextmanager
def db_session():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    if Config.DB_TYPE == 'sqlite':
        _init_sqlite()
    else:
        _init_pg()


def _init_sqlite():
    with db_session() as conn:
        c = conn.cursor()
        c.execute('PRAGMA foreign_keys=OFF')
        for stmt in _SCHEMA_SQLITE:
            c.execute(stmt)
        c.execute('PRAGMA foreign_keys=ON')
        conn.commit()


def _init_pg():
    if PG_V3:
        conn = psycopg.connect(Config.db_url(), prepare_threshold=None)
    else:
        conn = psycopg2.connect(Config.db_url())
    conn.autocommit = True
    try:
        c = conn.cursor()
        for stmt in _SCHEMA_PG:
            try: c.execute(stmt)
            except Exception as e:
                if 'already exists' not in str(e).lower(): raise
    finally:
        conn.close()


_SCHEMA_SQLITE = [
    """CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT (datetime('now','localtime')))""",
    """CREATE TABLE IF NOT EXISTS meters (meter_id TEXT NOT NULL, location TEXT DEFAULT '', usage_type TEXT DEFAULT '', ownership TEXT DEFAULT '', status TEXT DEFAULT 'active', user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT (datetime('now','localtime')), updated_at TIMESTAMP DEFAULT (datetime('now','localtime')), PRIMARY KEY (meter_id, user_id))""",
    """CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, meter_id TEXT NOT NULL, year_month TEXT NOT NULL, category TEXT NOT NULL CHECK(category IN ('电费支','电量支','电费收','电量收')), amount REAL DEFAULT 0, counterparty TEXT DEFAULT '', user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT (datetime('now','localtime')))""",
    "CREATE INDEX IF NOT EXISTS idx_tx_meter ON transactions(meter_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_month ON transactions(year_month)",
    "CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id)",
    """CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, user_id INTEGER DEFAULT 1, UNIQUE(name, user_id), created_at TIMESTAMP DEFAULT (datetime('now','localtime')))""",
    """CREATE TABLE IF NOT EXISTS customer_meters (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, meter_id TEXT NOT NULL, valid_from TEXT DEFAULT '', valid_to TEXT DEFAULT NULL, note TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS receivables (id INTEGER PRIMARY KEY AUTOINCREMENT, meter_id TEXT NOT NULL, year_month TEXT NOT NULL, receivable_amount REAL DEFAULT 0, received_amount REAL DEFAULT 0, customer_name TEXT DEFAULT '', status TEXT DEFAULT 'pending' CHECK(status IN ('pending','partial','paid')), confirmed_date TEXT DEFAULT '', received_date TEXT DEFAULT '', note TEXT DEFAULT '', user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT (datetime('now','localtime')), updated_at TIMESTAMP DEFAULT (datetime('now','localtime')))""",
    "CREATE INDEX IF NOT EXISTS idx_recv_user ON receivables(user_id)",
    """CREATE TABLE IF NOT EXISTS payment_history (id INTEGER PRIMARY KEY AUTOINCREMENT, receivable_id INTEGER NOT NULL, meter_id TEXT NOT NULL, year_month TEXT NOT NULL, amount REAL DEFAULT 0, payment_date TEXT DEFAULT '', customer_name TEXT DEFAULT '', created_at TIMESTAMP DEFAULT (datetime('now','localtime')))""",
    """CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, table_name TEXT NOT NULL, detail TEXT DEFAULT '', user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT (datetime('now','localtime')))""",
]

_SCHEMA_PG = [
    """CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name VARCHAR(200) UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS meters (meter_id VARCHAR(50) NOT NULL, location VARCHAR(500) DEFAULT '', usage_type VARCHAR(200) DEFAULT '', ownership VARCHAR(500) DEFAULT '', status VARCHAR(20) DEFAULT 'active', user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW(), PRIMARY KEY (meter_id, user_id))""",
    """CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, meter_id VARCHAR(50) NOT NULL, year_month VARCHAR(10) NOT NULL, category VARCHAR(10) NOT NULL CHECK(category IN ('电费支','电量支','电费收','电量收')), amount DOUBLE PRECISION DEFAULT 0, counterparty VARCHAR(500) DEFAULT '', user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW())""",
    "CREATE INDEX IF NOT EXISTS idx_tx_meter ON transactions(meter_id)",
    "CREATE INDEX IF NOT EXISTS idx_tx_month ON transactions(year_month)",
    "CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id)",
    """CREATE TABLE IF NOT EXISTS customers (id SERIAL PRIMARY KEY, name VARCHAR(500) NOT NULL, user_id INTEGER DEFAULT 1, UNIQUE(name, user_id), created_at TIMESTAMP DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS customer_meters (id SERIAL PRIMARY KEY, customer_id INTEGER NOT NULL, meter_id VARCHAR(50) NOT NULL, valid_from VARCHAR(20) DEFAULT '', valid_to VARCHAR(20) DEFAULT NULL, note VARCHAR(500) DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS receivables (id SERIAL PRIMARY KEY, meter_id VARCHAR(50) NOT NULL, year_month VARCHAR(10) NOT NULL, receivable_amount DOUBLE PRECISION DEFAULT 0, received_amount DOUBLE PRECISION DEFAULT 0, customer_name VARCHAR(500) DEFAULT '', status VARCHAR(10) DEFAULT 'pending' CHECK(status IN ('pending','partial','paid')), confirmed_date VARCHAR(20) DEFAULT '', received_date VARCHAR(20) DEFAULT '', note VARCHAR(500) DEFAULT '', user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""",
    "CREATE INDEX IF NOT EXISTS idx_recv_user ON receivables(user_id)",
    """CREATE TABLE IF NOT EXISTS payment_history (id SERIAL PRIMARY KEY, receivable_id INTEGER NOT NULL, meter_id VARCHAR(50) NOT NULL, year_month VARCHAR(10) NOT NULL, amount DOUBLE PRECISION DEFAULT 0, payment_date VARCHAR(20) DEFAULT '', customer_name VARCHAR(500) DEFAULT '', created_at TIMESTAMP DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS audit_log (id SERIAL PRIMARY KEY, action VARCHAR(50) NOT NULL, table_name VARCHAR(50) NOT NULL, detail VARCHAR(1000) DEFAULT '', user_id INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT NOW())""",
    "INSERT INTO users (name) VALUES ('管理员') ON CONFLICT (name) DO NOTHING",
]
