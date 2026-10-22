from datetime import UTC, datetime, time, timedelta

import pytest

from py_livewire import (
    Bike,
    ChargingSchedule,
    ChargingStatus,
    Location,
    TirePressure,
    uuid_from_android_id,
)
from py_livewire.utils import device_uuids_in_log, to_float, to_timedelta

# Shapes as returned by the live backend, identifiers anonymized


def test_charging_status_numbers():
    status = ChargingStatus.from_dict(
        {
            "bikeChargingData": {
                "batteryPercentage": 50,
                "chargingStatus": False,
                "durationElapsed": "2",
                "durationUnit": "days",
                "maxLimit": 90,
                "odometer": 1000.5,
                "pluggedIn": False,
                "range": 44,
                "timeToMaxLimit": "0.0",
            },
            "trackingStatus": "SAFE",
        }
    )

    assert status.battery_level == 50
    assert status.charge_limit == 90
    assert not status.charging and not status.plugged_in
    assert status.range_km == pytest.approx(70.81, abs=0.01)
    assert status.odometer_km == pytest.approx(1610.15, abs=0.01)
    assert status.data_age == timedelta(days=2)
    assert status.time_to_limit == timedelta(0)
    assert status.tracking_status == "SAFE"


def test_charging_status_strings():
    # the app models these fields as strings, so the backend may send them as such
    status = ChargingStatus.from_dict(
        {
            "bikeChargingData": {
                "batteryPercentage": "65",
                "chargingStatus": True,
                "durationElapsed": "5",
                "durationUnit": "seconds",
                "maxLimit": 80,
                "odometer": "550.63",
                "pluggedIn": True,
                "range": "68",
                "timeToMaxLimit": "45",
            },
        }
    )

    assert status.battery_level == 65
    assert status.charging and status.plugged_in
    assert status.odometer_miles == pytest.approx(550.63)
    assert status.time_to_limit == timedelta(minutes=45)
    assert status.data_age == timedelta(seconds=5)
    assert status.tracking_status is None


def test_charging_status_empty():
    status = ChargingStatus.from_dict({})
    assert status.battery_level is None
    assert status.charge_limit is None
    assert status.range_km is None


BIKE = {
    "id": "100000001",
    "modifiedTime": "2025-10-18 13:12:31+0000",
    "createdTime": "2025-10-18 13:12:31+0000",
    "vin": "7TM3GDYD6SB000000",
    "year": 2025,
    "make": "LiveWire",
    "model": "S2 Mulholland",
    "name": "Mulholland",
    "primaryBike": True,
    "color": "Liquid Black / Black",
    "colorCode": "M36",
    "modelNumber": "3GDY",
    "modelCode": "S2MH",
    "brandShortName": "LW",
}


def test_bike():
    bike = Bike.from_dict({**BIKE, "pairingStatus": True})
    assert bike.id == "100000001"
    assert bike.model_code == "S2MH"
    assert bike.year == 2025
    assert bike.primary
    assert bike.paired is True
    assert bike.created == datetime(2025, 10, 18, 13, 12, 31, tzinfo=UTC)

    assert Bike.from_dict(BIKE).paired is None


def test_location():
    location = Location.from_dict(
        {
            "vin": "7TM3GDYD6SB000000",
            "iccid": "0",
            "tcu_timestamp": "2026-09-11T16:23:56.000Z",
            "viot_timestamp": "2026-09-11T16:23:58.350Z",
            "latitude": 48.1371,
            "longitude": 11.5754,
            "speed_km": 0.0,
            "altitude": 510.5,
            "gps_time": "2026-09-11T16:22:33.000Z",
            "fix_type": 3,
        }
    )
    assert (location.latitude, location.longitude) == (48.1371, 11.5754)
    assert location.gps_time == datetime(2026, 9, 11, 16, 22, 33, tzinfo=UTC)
    assert location.fix_type == 3


def test_tire_pressure():
    pressure = TirePressure.from_dict(
        {
            "code": 0,
            "detail": "",
            "FrontTireLow": 0,
            "RearTireLow": 1,
            "TirePressureFront": {"UnitOfMeasure": "psi", "value": "36.5"},
            "TirePressureRear": {"UnitOfMeasure": "psi", "value": "38"},
            "RecomendedTirePressureFront": {"UnitOfMeasure": "psi", "value": "36"},
            "RecomendedTirePressureRear": {"UnitOfMeasure": "psi", "value": "42"},
        }
    )
    assert (pressure.front, pressure.rear) == (36.5, 38)
    assert (pressure.front_recommended, pressure.rear_recommended) == (36, 42)
    assert pressure.unit == "psi"
    assert not pressure.front_low and pressure.rear_low


def test_charging_schedule():
    schedule = ChargingSchedule.from_dict(
        {
            "scheduleId": "s1",
            "status": "ACTIVE",
            "timezoneOffsetMinutes": 120,
            "days": ["Mon", "Tue"],
            "time": {"start": "22:00", "end": "06:00"},
        }
    )
    assert schedule.enabled
    assert schedule.days == ["Mon", "Tue"]
    assert (schedule.start, schedule.end) == (time(22), time(6))
    assert schedule.timezone_offset_minutes == 120


@pytest.mark.parametrize(
    "value, expected",
    [
        (4, 4.0),
        ("4", 4.0),
        ("0.0", 0.0),
        (" 87.5 ", 87.5),
        (None, None),
        ("", None),
        ("--", None),
        (True, None),
    ],
)
def test_to_float(value, expected):
    assert to_float(value) == expected


def test_to_timedelta():
    assert to_timedelta("3", "Hours") == timedelta(hours=3)
    assert to_timedelta("1", "minute") == timedelta(minutes=1)
    assert to_timedelta("1", "fortnights") is None
    assert to_timedelta(None, "days") is None


def test_uuid_from_android_id():
    # Java: UUID.nameUUIDFromBytes("test".getBytes())
    assert uuid_from_android_id("test") == "098f6bcd-4621-3373-8ade-4e832627b4f6"


def test_device_uuids_in_log():
    log = "\n".join(
        [
            # logcat -v tag
            "D/## UUID ##: 098f6bcd-4621-3373-8ade-4e832627b4f6",
            "I/Other   : session 6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            # logcat -v threadtime
            "10-22 14:03:11.204  8123  8123 D ## UUID ##: "
            "098f6bcd-4621-3373-8ade-4e832627b4f6",
            "10-22 14:05:42.019  8123  8123 D ## UUID ##: "
            "4032af8d-6103-3123-906e-58e067140cc5",
            "D/## UUID ##: null",
        ]
    )
    assert device_uuids_in_log(log) == [
        "098f6bcd-4621-3373-8ade-4e832627b4f6",
        "4032af8d-6103-3123-906e-58e067140cc5",
    ]
    assert device_uuids_in_log("") == []
