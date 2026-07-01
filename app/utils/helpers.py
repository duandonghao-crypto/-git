"""Utility helpers."""
import re
import email
from datetime import datetime


def sanitize_filename(name: str) -> str:
    """Remove illegal filename characters."""
    return re.sub(r'[\\/*?:"<>|]', '_', name)


def decode_filename(encoded_name) -> str:
    """Decode email header encoded filename."""
    if not encoded_name:
        return ""
    try:
        parts = email.header.decode_header(encoded_name)
        result = ""
        for part, charset in parts:
            if isinstance(part, bytes):
                try:
                    result += part.decode(charset or 'utf-8', errors='replace')
                except Exception:
                    result += part.decode('utf-8', errors='replace')
            else:
                result += str(part)
        return result
    except Exception:
        return str(encoded_name)


def parse_year_month(raw: str) -> str | None:
    """Parse various year-month formats into 'YYYY-MM'.
    Supports: '2026年5月', '202605', '2026-05'"""
    m = re.search(r'(\d{4})\s*年\s*(\d{1,2})', raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r'(\d{4})-?(\d{2})', raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r'(\d{6})', raw)
    if m:
        s = m.group(1)
        return f"{s[:4]}-{int(s[4:]):02d}"
    return None


def parse_amount(value) -> float:
    """Parse a numeric amount from various string formats."""
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(',', '').replace('，', ''))
    except (ValueError, TypeError):
        return 0.0


def strip_meter_id(raw: str) -> str:
    """Strip brackets from meter ID: '[123]' -> '123'."""
    return raw.strip().replace('[', '').replace(']', '')
