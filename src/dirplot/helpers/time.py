"""Human-readable time period parsing."""

import re
from datetime import datetime, timedelta, timezone

LAST_RE = re.compile(r"^(\d+)(mo|m|h|d|w)$")


def parse_last_period(value: str) -> datetime:
    """Parse a human period string into an absolute UTC datetime.

    Units: m=minutes, h=hours, d=days, w=weeks, mo=months (30d each).
    Examples: '10d', '24h', '2w', '1mo', '30m'
    """
    match = LAST_RE.match(value.strip().lower())
    if not match:
        raise ValueError(
            f"Invalid --period value {value!r}. "
            "Expected a number + unit: h, d, w, mo  (e.g. 24h, 10d, 2w, 1mo)."
        )
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400, "mo": 30 * 86400}[unit]
    return datetime.now(tz=timezone.utc) - timedelta(seconds=amount * seconds)
