# py-livewire

Async Python client for the LiveWire motorcycle cloud: the same API the LiveWire EV app
(Android 1.9.0) uses, covering bikes, pairing, charging status and control, position, tire
pressure, analytics, charging schedules, maintenance, roadside assistance, rides and dealers.

> This project is not affiliated with LiveWire or Harley-Davidson. It uses an undocumented
> API that may change or stop working at any time.

## The device UUID

Every session with the backend is opened for a *device UUID*. The app generates it on the
phone (`UUID.nameUUIDFromBytes(ANDROID_ID)`); it is no secret, just an identifier. The backend
only answers the **charging status** for device UUIDs that are **paired** with the bike, and
otherwise returns error code `3000` ("Command manager api failed"), raised as `NotPairedError`.
In testing, other data like the position, tire pressure and analytics was also served to
unpaired UUIDs.

There are two ways to get a paired UUID:

- **Pair a new one** (recommended). Pairing happens through the cloud, no Bluetooth needed:
  the backend makes the bike show a 6-digit code on its display, which is sent back. You have
  to be at the bike once, with the ignition on, not in propulsion mode, not charging and with
  cellular reception. `livewire pair` does this and prints the UUID to keep.
- **Reuse an already paired UUID**, e.g. the one of your phone, see below.

A paired UUID keeps working across logins. A new UUID needs pairing again.

### Finding your phone's UUID

The app doesn't show the UUID anywhere, but it writes it to the Android system log (logcat)
with the tag `## UUID ##` whenever it uses it, including on launch. The log can be read without
root:

- **From a computer:** enable USB (or wireless) debugging on the phone, connect it, and run
  `livewire phone-uuid`, then open the LiveWire app. This needs `adb` from the
  Android platform tools. By hand, `adb logcat -v tag | grep "## UUID ##"` shows the same.
- **On the phone alone** (Android 11+): enable wireless debugging and run `adb logcat` from a
  local adb client such as LADB or `adb` in Termux, or use a log viewer app after granting it
  access once with `adb shell pm grant <app package> android.permission.READ_LOGS`.

With root, the UUID is in `/data/data/com.livewire.arrow/shared_prefs/locale.xml`, key
`device_uuid`. The UUID survives reinstalling the app, but changes with a factory reset.

Other routes don't work. Another app can't compute the UUID, because the device ID it is
derived from differs per app since Android 8. The app is excluded from backups, and it trusts
no user-installed certificates, so a TLS proxy needs root. Also, the backend's list of paired
devices answers HTTP 401.

Some phone makers' builds drop the debug log messages this relies on.

## Installation

Python 3.11 or newer.

```
pip install py-livewire
```

This also installs the `livewire` command line tool (or run `python -m py_livewire`).

## Command line

Credentials come from `LW_EMAIL` and `LW_PASSWORD` (prompted for otherwise), the device UUID
from `LW_DEVICE_UUID` or `--device-uuid`.

```
livewire pair       # once, at the bike: pairs a new UUID and prints it
export LW_DEVICE_UUID=<the printed UUID>
livewire status     # battery, charging, range, odometer, position
livewire bikes      # bikes of the account and their pairing state
```

With several bikes on the account, choose one with `--bike <id or VIN>`.

## Library

```python
import asyncio

from py_livewire import Client


async def main():
    async with Client("user@example.org", "password", device_uuid="…") as client:
        bike = (await client.get_bikes())[0]

        status = await client.get_charging_status(bike.id)
        print(status.battery_level, status.range_km, status.charging)

        location = await client.get_location(bike.id)
        print(location.latitude, location.longitude)


asyncio.run(main())
```

Pairing from code: `await client.pair(bike.id, get_code)`, where `get_code` is a plain or
coroutine function returning the code from the bike's display. Afterwards `client.device_uuid`
is the UUID to keep.

`Client` logs in on the first request, and logs in again once if the backend rejects the
session token. Pass `session=` to use your own `aiohttp.ClientSession`.

### Methods

| Area | Methods |
|---|---|
| Bikes | `get_bikes`, `get_vin_info`, `add_bike`, `update_bike`, `delete_bike` |
| Pairing | `is_paired`, `pair`, `request_pairing_code`, `verify_pairing_code`, `get_paired_users`, `request_unpairing_code`, `verify_unpairing_code` |
| Vehicle data | `get_charging_status`, `get_location`, `get_tire_pressure`, `get_software_versions`, `get_software_release_notes`, `get_charging_analytics`, `get_ride_analytics` |
| Charging | `set_charge_limit`, `start_charging`, `get_charging_schedules`, `add_charging_schedule`, `update_charging_schedule`, `delete_charging_schedule` |
| Tracking | `set_enhanced_tracking`, `set_tracking_consent` |
| Maintenance | `get_maintenance_records`, `get_maintenance_schedule`, `add/update/delete_maintenance_record`, `get/add/update/delete_roadside_assistance` |
| Rides | `get_rides`, `get_my_rides`, `get_ride`, `get_shared_ride`, `save_ride`, `update_ride`, `rename_ride`, `delete_ride`, `convert_recorded_ride`, `get_bookmarked_rides`, `bookmark_ride`, `remove_bookmark` |
| Dealers | `get_dealers` |
| Account and app | `get_notification_settings`, `update_notification_setting`, `set_language`, `get_external_urls`, `get_app_config`, `get_minimum_app_version`, `get_release_notes`, `get_countries`, `delete_account` |

Vehicle data comes as dataclasses (`Bike`, `ChargingStatus`, `Location`, `TirePressure`,
`ChargingSchedule`, `PairedUser`, `SoftwareVersion`), each with the full response in `raw`.
Range and odometer arrive in miles; `ChargingStatus` also offers them in km. The rest returns
the parsed JSON.

Errors are `AuthenticationError`, `ApiError` (with `code` and `status`), its subclass
`NotPairedError`, and `PairingError`, all derived from `LivewireError`.

### Backend quirks

- Errors mostly arrive with HTTP 200 as `{"error": {"code": …, "description": …}}`.
- Numbers like the battery level arrive as JSON numbers or strings; both are handled.
- `get_paired_users` was answered with HTTP 401 in testing, even for a paired UUID.
- There is no working endpoint to cancel a pairing request; the app's is broken. An unused code
  expires.
- The app's endpoints for ride tags and the home screen battery status no longer exist on the
  backend and are left out.

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```

The tests run against a local fake backend and need no account.

To release, bump `__version__` in `py_livewire/__init__.py` and push a `v*` tag (or
publish a GitHub release); the PyPI Release workflow tests, builds and uploads it.
