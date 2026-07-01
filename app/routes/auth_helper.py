"""Auth and SQL helpers for routes."""
from flask import session
from config import Config


def user_id():
    return session.get('user_id', 1)


def user_name():
    return session.get('user_name', '')


def ph():
    return '?' if Config.DB_TYPE == 'sqlite' else '%s'


def now():
    return "datetime('now','localtime')" if Config.DB_TYPE == 'sqlite' else 'NOW()'


def q(sql, params=None):
    """Replace {ph} and {now} placeholders, return (sql, params)."""
    sql = sql.replace('{ph}', ph()).replace('{now}', now())
    return sql, params or ()


def exec_db(conn, sql, params=None):
    """Execute SQL with placeholder handling."""
    sql = sql.replace('{ph}', ph()).replace('{now}', now())
    c = conn.cursor()
    c.execute(sql, params or ())
    return c


