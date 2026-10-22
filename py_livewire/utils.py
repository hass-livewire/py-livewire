import hashlib
import math
import re
import uuid
from datetime import datetime, timedelta
from typing import Any


def to_float(value: Any) -> float | None:
    """Convert a number arriving as JSON number or string, None if unparseable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        res = float(value)
    except (TypeError, ValueError):
        return None
    return res if math.isfinite(res) else None


def to_int(value: Any) -> int | None:
    res = to_float(value)
    return None if res is None else int(res)


def to_bool(value: Any) -> bool | None:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        return {"true": True, "false": False}.get(value.strip().lower())
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def to_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


_DURATION_UNITS = {
    "second": "seconds",
    "minute": "minutes",
    "hour": "hours",
    "day": "days",
    "week": "weeks",
}


def to_timedelta(value: Any, unit: str | None) -> timedelta | None:
    """Convert a value like ("2", "days") as used by the charging status."""
    amount = to_float(value)
    if amount is None or not unit:
        return None
    name = _DURATION_UNITS.get(unit.strip().lower().rstrip("s"))
    return timedelta(**{name: amount}) if name else None


def uuid_from_android_id(android_id: str) -> str:
    """Derive the device UUID the Android app uses from an ANDROID_ID.

    The app computes UUID.nameUUIDFromBytes(ANDROID_ID), i.e. an MD5 based version 3
    UUID without namespace. Since Android 8 the ANDROID_ID differs per app signing key,
    so the value of "adb shell settings get secure android_id" is not the one the app
    sees; with root it is in /data/system/users/0/settings_ssaid.xml. Easier is reading
    the UUID the app logs, see device_uuids_in_log().
    """
    digest = hashlib.md5(android_id.encode()).digest()
    return str(uuid.UUID(bytes=digest, version=3))


# The app logs its device UUID with this tag whenever it uses it, e.g. on launch
LOG_TAG = "## UUID ##"

_LOGGED_UUID = re.compile(
    re.escape(LOG_TAG)
    + r".*?\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
    re.IGNORECASE,
)


def device_uuids_in_log(log: str) -> list[str]:
    """Device UUIDs the app logged in logcat output, in order, without repeats."""
    return list(dict.fromkeys(_LOGGED_UUID.findall(log)))
