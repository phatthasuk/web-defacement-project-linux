from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime.

    Session timestamps are stored as naive UTC values (SQLite does not persist
    timezone information), so every comparison against them must use a naive UTC
    value too. Centralising this avoids mixing offset-aware and offset-naive
    datetimes, which raises TypeError when compared.
    """
    return datetime.now(UTC).replace(tzinfo=None)
