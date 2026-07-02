"""Database module — PostgreSQL (pg8000, pure Python) or SQLite."""
import os, sqlite3
from contextlib import contextmanager

try:
    import pg8000.native
    HAS_PG = True
except ImportError:
    HAS_PG = False

from config import Config


class _Connection:
    """Wrap pg8000 connection to look like psycopg2 connection."""
    def __init__(self, conn):
        self._conn = conn
        self.autocommit = True
    def commit(self):
        self._conn.run('COMMIT')
    def rollback(self):
        self._conn.run('ROLLBACK')
    def close(self):
        self._conn.close()
    def cursor(self):
        return _Cursor(self._conn)


def get_db():
    if Config.DB_TYPE == 'sqlite':
        conn = sqlite3.connect(getattr(Config, 'SQLITE_PATH', ':memory:'))
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        return conn
    if not HAS_PG:
        raise RuntimeError('pg8000 not installed')
    url = Config.db_url()
    from urllib.parse import urlparse, parse_qs
    u = urlparse(url)
    kwargs = dict(host=u.hostname, port=u.port or 5432, user=u.username, password=u.password, database=u.path.lstrip('/'))
    qs = parse_qs(u.query)
    if 'sslmode' in qs: kwargs['ssl_context'] = None
    raw = pg8000.native.Connection(**kwargs)
    conn = _Connection(raw)
    conn.autocommit = False
    return conn


class _Cursor:
    """Wrap pg8000 cursor to look like psycopg2 cursor.
    fetchone/fetchall return dicts with [0] index support."""
    def __init__(self, conn):
        self._conn = conn
        self._cols = []
        self._rows = []

    def execute(self, sql, params=None):
        if params:
            # pg8000 uses :param style
            if isinstance(params, (list, tuple)) and params:
                import re
                param_dict = {}
                def repl(m):
                    nonlocal param_dict
                    i = len(param_dict)
                    key = f'p{i}'
                    param_dict[key] = params[i]
                    return f':{key}'
                sql = re.sub(r'%s', repl, sql)
                self._rows = self._conn.run(sql, **param_dict) if param_dict else []
            else:
                self._rows = self._conn.run(sql, params)
        else:
            self._rows = self._conn.run(sql)
        self._cols = [c['name'] for c in (self._conn.columns or [])]
        self._pos = 0

    def fetchone(self):
        if self._pos >= len(self._rows):
            return None
        r = self._rows[self._pos]
        self._pos += 1
        return _Row(self._cols, r) if self._cols else r

    def fetchall(self):
        return [_Row(self._cols, r) for r in self._rows[self._pos:]] if self._cols else self._rows[self._pos:]

    @property
    def rowcount(self):
        return len(self._rows)

    @property
    def description(self):
        return self._cols

    def close(self):
        pass


class _Row:
    """Dict-like row with [0] index support."""
    def __init__(self, cols, values):
        self._d = dict(zip(cols, values))
        self._keys = cols
    def __getitem__(self, k):
        if isinstance(k, int): k = self._keys[k]
        return self._d[k]
    def keys(self): return self._d.keys()
    def values(self): return self._d.values()
    def items(self): return self._d.items()
    def get(self, k, d=None): return self._d.get(k, d)
    def __contains__(self, k): return k in self._d
    def __iter__(self): return iter(self._d)
    def __repr__(self): return repr(self._d)


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
    conn = pg8000.native.Connection(
        host=Config.pg_host(), port=Config.pg_port(),
        user=Config.pg_user(), password=Config.pg_pass(),
        database=Config.pg_db()
    )
    try:
        for stmt in _SCHEMA_PG:
            try: conn.run(stmt)
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
