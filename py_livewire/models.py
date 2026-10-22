from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from .const import KM_PER_MILE
from .utils import to_bool, to_datetime, to_float, to_int, to_timedelta


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def _miles_to_km(value: float | None) -> float | None:
    return None if value is None else value * KM_PER_MILE


@dataclass
class Bike:
    id: str
    vin: str | None
    name: str | None
    make: str | None
    model: str | None
    model_code: str | None
    model_number: str | None
    year: int | None
    color: str | None
    created: datetime | None
    primary: bool
    # Whether the client's device UUID is paired with the bike, None if the
    # response did not tell
    paired: bool | None
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Bike":
        return cls(
            id=str(data["id"]),
            vin=data.get("vin"),
            name=data.get("name"),
            make=data.get("make"),
            model=data.get("model"),
            model_code=data.get("modelCode"),
            model_number=data.get("modelNumber"),
            year=to_int(data.get("year")),
            color=data.get("color"),
            created=to_datetime(data.get("createdTime")),
            primary=bool(to_bool(data.get("primaryBike"))),
            paired=to_bool(data.get("pairingStatus")),
            raw=data,
        )


@dataclass
class ChargingStatus:
    battery_level: float | None  # percent
    charging: bool
    plugged_in: bool
    charge_limit: int | None  # percent
    time_to_limit: timedelta | None
    range_miles: float | None
    odometer_miles: float | None
    # How long ago the bike reported this data
    data_age: timedelta | None
    # Enhanced vehicle tracking: SAFE, STOLEN or PENDING
    tracking_status: str | None
    raw: dict[str, Any] = field(repr=False)

    @property
    def range_km(self) -> float | None:
        return _miles_to_km(self.range_miles)

    @property
    def odometer_km(self) -> float | None:
        return _miles_to_km(self.odometer_miles)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChargingStatus":
        status = data.get("bikeChargingData") or {}
        time_to_limit = to_float(status.get("timeToMaxLimit"))

        return cls(
            battery_level=to_float(status.get("batteryPercentage")),
            charging=bool(to_bool(status.get("chargingStatus"))),
            plugged_in=bool(to_bool(status.get("pluggedIn"))),
            charge_limit=to_int(status.get("maxLimit")) or None,
            time_to_limit=None
            if time_to_limit is None
            else timedelta(minutes=time_to_limit),
            range_miles=to_float(status.get("range")),
            odometer_miles=to_float(status.get("odometer")),
            data_age=to_timedelta(
                status.get("durationElapsed"), status.get("durationUnit")
            ),
            tracking_status=data.get("trackingStatus"),
            raw=data,
        )


@dataclass
class Location:
    latitude: float | None
    longitude: float | None
    altitude: float | None  # meters
    speed_kmh: float | None
    gps_time: datetime | None
    reported_at: datetime | None
    fix_type: int | None
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Location":
        return cls(
            latitude=to_float(data.get("latitude")),
            longitude=to_float(data.get("longitude")),
            altitude=to_float(data.get("altitude")),
            speed_kmh=to_float(data.get("speed_km")),
            gps_time=to_datetime(data.get("gps_time")),
            reported_at=to_datetime(data.get("tcu_timestamp")),
            fix_type=to_int(data.get("fix_type")),
            raw=data,
        )


@dataclass
class TirePressure:
    front: float | None
    rear: float | None
    front_recommended: float | None
    rear_recommended: float | None
    unit: str | None
    front_low: bool
    rear_low: bool
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TirePressure":
        front = data.get("TirePressureFront") or {}
        rear = data.get("TirePressureRear") or {}

        def value(key: str) -> float | None:
            return to_float((data.get(key) or {}).get("value"))

        return cls(
            front=to_float(front.get("value")),
            rear=to_float(rear.get("value")),
            # sic, the backend misspells these
            front_recommended=value("RecomendedTirePressureFront"),
            rear_recommended=value("RecomendedTirePressureRear"),
            unit=front.get("UnitOfMeasure") or rear.get("UnitOfMeasure"),
            front_low=bool(to_int(data.get("FrontTireLow"))),
            rear_low=bool(to_int(data.get("RearTireLow"))),
            raw=data,
        )


def _to_time(value: Any) -> time | None:
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ChargingSchedule:
    id: str
    # ACTIVE, INACTIVE or PENDING while the bike has not confirmed a change yet
    status: str | None
    days: list[str]
    # Local time of the offset below, the window may cross midnight
    start: time | None
    end: time | None
    timezone_offset_minutes: int | None
    raw: dict[str, Any] = field(repr=False)

    @property
    def enabled(self) -> bool:
        return (self.status or "").upper() == "ACTIVE"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChargingSchedule":
        window = data.get("time") or {}

        return cls(
            id=str(data.get("scheduleId")),
            status=data.get("status"),
            days=list(data.get("days") or []),
            start=_to_time(window.get("start")),
            end=_to_time(window.get("end")),
            timezone_offset_minutes=to_int(data.get("timezoneOffsetMinutes")),
            raw=data,
        )


@dataclass
class PairedUser:
    user_id: str | None
    device_uuid: str | None
    device_model: str | None
    device_type: str | None
    email: str | None
    first_name: str | None
    last_name: str | None
    paired_since: datetime | None
    ready_to_unpair: bool
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PairedUser":
        return cls(
            user_id=_str(data.get("userId")),
            device_uuid=data.get("deviceUUID"),
            device_model=data.get("deviceModel"),
            device_type=data.get("deviceType"),
            email=data.get("userEmail"),
            first_name=data.get("userFirstName"),
            last_name=data.get("userLastName"),
            paired_since=to_datetime(data.get("createdTime")),
            ready_to_unpair=bool(to_bool(data.get("readyToUnpair"))),
            raw=data,
        )


@dataclass
class SoftwareVersion:
    bike_id: str
    vin: str | None
    current: str | None
    latest: str | None
    # MATCH, MISMATCH or NEW_FEATURE_AVAILABLE
    status: str | None
    feature_ids: list[str]
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SoftwareVersion":
        return cls(
            bike_id=str(data.get("bikeId")),
            vin=data.get("vin"),
            current=data.get("currentVsbVersion"),
            latest=data.get("maxAvailableVsbVersion"),
            status=data.get("vsbMatchStatus"),
            feature_ids=list(data.get("featureIds") or []),
            raw=data,
        )
