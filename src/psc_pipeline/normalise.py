"""Number, jurisdiction and date normalisation. Rules: spec 02 section 1."""
import re
from datetime import date

VALID_NUMBER = re.compile(r"^(\d{8}|[A-Z]{2}\d{6}|R\d{7})$", re.ASCII)
PREFIX_SHORT = re.compile(r"^([A-Z]{2})(\d{1,6})$", re.ASCII)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)
UK = re.compile(
    r"england|wales|scotland|northern ireland|united kingdom|\buk\b|great britain|companies house|cardiff",
    re.IGNORECASE,
)
FILE_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def normalise_number(raw) -> str | None:
    """Company or registration number -> canonical form, or None if missing/unrecognised."""
    if not isinstance(raw, str):
        return None
    s = re.sub(r"\s+", "", raw).upper()
    if not s.isascii():
        return None
    if s.isdigit() and len(s) <= 8:
        s = s.zfill(8)
    elif m := PREFIX_SHORT.match(s):
        s = m.group(1) + m.group(2).zfill(6)
    return s if VALID_NUMBER.match(s) else None


def is_uk(country: str | None, place: str | None) -> bool | None:
    """True/False for UK registration; None when neither field is present."""
    text = " ".join(v for v in (country, place) if isinstance(v, str) and v.strip())
    if not text:
        return None
    return bool(UK.search(text))


def parse_date(raw) -> tuple[date | None, str | None]:
    """Source date -> (date, issue code). Issue is None, 'date_timestamp_truncated' or 'invalid_date'."""
    if raw is None:
        return None, None
    if not isinstance(raw, str):
        return None, "invalid_date"
    value, issue = raw.strip(), None
    if len(value) > 10 and value[10] == "T":
        value, issue = value[:10], "date_timestamp_truncated"
    if not ISO_DATE.match(value):  # fromisoformat alone also accepts week dates like 2020-W01-1
        return None, "invalid_date"
    try:
        return date.fromisoformat(value), issue
    except ValueError:
        return None, "invalid_date"


def date_from_filename(name: str) -> date | None:
    m = FILE_DATE.search(name)
    try:
        return date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None
