"""Command line access to the LiveWire API.

    livewire bikes
    livewire status [--bike ID_OR_VIN]
    livewire pair [--bike ID_OR_VIN]
    livewire phone-uuid [--timeout SECONDS]

Credentials are read from LW_EMAIL and LW_PASSWORD, or prompted for. The device UUID is
read from LW_DEVICE_UUID or --device-uuid; pair generates a new one if none is given.
phone-uuid reads the UUID the phone app logs, through adb, and needs no credentials.
"""

import argparse
import asyncio
import getpass
import os
import sys
import uuid
from datetime import timedelta

from . import Bike, Client, LivewireError, NotPairedError
from .utils import device_uuids_in_log


def device_uuid(value: str) -> str:
    uuid.UUID(value)
    return value


def _choose_bike(bikes: list[Bike], selector: str | None) -> Bike:
    if selector:
        for bike in bikes:
            if selector in (bike.id, bike.vin):
                return bike
        sys.exit(f"No bike with id or VIN {selector} on this account.")

    if not bikes:
        sys.exit("No bikes on this account.")
    if len(bikes) > 1:
        sys.exit("Several bikes on this account, choose one with --bike.")
    return bikes[0]


def _ago(age: timedelta) -> str:
    n, unit = int(age.total_seconds()), "second"
    for name, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if n >= size:
            n, unit = n // size, name
            break
    return f"{n} {unit}{'' if n == 1 else 's'} ago"


def _num(value: float | None, unit: str) -> str:
    return "-" if value is None else f"{value:.0f}{unit}"


def _distance(km: float | None, miles: float | None) -> str:
    return f"{_num(km, ' km')} ({_num(miles, ' mi')})"


def _describe(bike: Bike) -> str:
    return f'{bike.year} {bike.model} "{bike.name}" (id {bike.id}, VIN {bike.vin})'


async def _bikes(client: Client, args: argparse.Namespace) -> None:
    for bike in await client.get_bikes():
        print(f"{_describe(bike)}, {'paired' if bike.paired else 'not paired'}")


async def _status(client: Client, args: argparse.Namespace) -> None:
    bike = _choose_bike(await client.get_bikes(), args.bike)
    print(_describe(bike))

    try:
        status = await client.get_charging_status(bike.id)
    except NotPairedError:
        sys.exit(
            "This device UUID is not paired with the bike, run `livewire pair` first."
        )

    if status.charging:
        charging = "yes" + (
            f", {status.time_to_limit} to the limit" if status.time_to_limit else ""
        )
    else:
        charging = "no, " + ("plugged in" if status.plugged_in else "not plugged in")

    limit = _num(status.charge_limit, "%")
    print(f"Battery:   {_num(status.battery_level, '%')} (limit {limit})")
    print(f"Charging:  {charging}")
    print(f"Range:     {_distance(status.range_km, status.range_miles)}")
    print(f"Odometer:  {_distance(status.odometer_km, status.odometer_miles)}")
    print(f"Reported:  {_ago(status.data_age) if status.data_age else '-'}")
    print(f"Tracking:  {status.tracking_status or '-'}")

    location = await client.get_location(bike.id)
    if location.latitude is not None:
        position = f"{location.latitude:.5f}, {location.longitude:.5f}"
        print(f"Position:  {position} at {location.gps_time or '-'}")


async def _pair(client: Client, args: argparse.Namespace) -> None:
    bike = _choose_bike(await client.get_bikes(), args.bike)
    print(_describe(bike))

    if bike.paired:
        print("This device UUID is already paired with the bike.")
    else:
        print("\nAt the bike, switch the ignition on and wait for the display.")
        print("The bike must not be in propulsion mode or charging, and needs")
        print("cellular reception.")
        await asyncio.to_thread(input, "Press Enter to request a pairing code... ")

        await client.pair(
            bike.id, lambda: asyncio.to_thread(input, "Code shown on the display: ")
        )
        print("Paired.")

    print(f"\nDevice UUID: {client.device_uuid}")
    print("Keep it, e.g. as LW_DEVICE_UUID. A different UUID needs pairing again.")


async def _adb(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "adb",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return await proc.wait(), out.decode(errors="replace")


async def _watch_log(timeout: float) -> list[str]:
    # The tag is matched here rather than with "logcat -s", which would pass it
    # through the phone's shell
    proc = await asyncio.create_subprocess_exec(
        "adb",
        "logcat",
        "-v",
        "tag",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert proc.stdout is not None  # a pipe, as requested
    try:
        async with asyncio.timeout(timeout):
            async for line in proc.stdout:
                if found := device_uuids_in_log(line.decode(errors="replace")):
                    return found
    except TimeoutError:
        pass
    finally:
        proc.kill()
        await proc.wait()
    return []


async def _phone_uuid(args: argparse.Namespace) -> None:
    try:
        code, state = await _adb("get-state")
    except FileNotFoundError:
        sys.exit("adb not found, install the Android platform tools.")
    if code != 0 or state.strip() != "device":
        sys.exit(
            f"No phone ready for adb ({state.strip() or 'no output'}). Enable USB or "
            "wireless debugging and connect the phone; with several devices, choose "
            "one with ANDROID_SERIAL."
        )

    _, log = await _adb("logcat", "-d", "-v", "tag")
    found = device_uuids_in_log(log)
    if not found:
        print(
            "Open the LiveWire app on the phone, close it first if it runs. "
            f"Waiting {args.timeout:.0f} s..."
        )
        found = await _watch_log(args.timeout)
    if not found:
        sys.exit(
            "The LiveWire app logged no device UUID. "
            "Some phones drop the app's debug log messages."
        )

    print(f"Device UUID: {found[-1]}")
    if len(found) > 1:
        print(f"(also logged earlier: {', '.join(found[:-1])})")
    print(f"Check it with: livewire --device-uuid {found[-1]} status")


async def _run(args: argparse.Namespace) -> None:
    email = os.environ.get("LW_EMAIL")
    if not email:
        email = await asyncio.to_thread(input, "LiveWire account email: ")
        email = email.strip()
    password = os.environ.get("LW_PASSWORD")
    if not password:
        password = await asyncio.to_thread(getpass.getpass, "Password: ")

    if args.device_uuid is None and args.command != "pair":
        print(
            "No device UUID given (LW_DEVICE_UUID or --device-uuid), "
            "using an unpaired one.",
            file=sys.stderr,
        )

    async with Client(email, password, args.device_uuid) as client:
        await {"bikes": _bikes, "status": _status, "pair": _pair}[args.command](
            client, args
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="livewire", description="LiveWire motorcycle cloud API"
    )
    parser.add_argument(
        "--device-uuid",
        type=device_uuid,
        default=os.environ.get("LW_DEVICE_UUID"),
        help="device UUID paired with the bike (default: $LW_DEVICE_UUID)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bikes", help="list the bikes of the account")
    for name, help in (
        ("status", "show charging status and position"),
        ("pair", "pair the device UUID with a bike"),
    ):
        command = commands.add_parser(name, help=help)
        command.add_argument(
            "--bike", help="id or VIN of the bike, needed with several bikes"
        )
    command = commands.add_parser(
        "phone-uuid", help="read the device UUID the phone app logs, through adb"
    )
    command.add_argument(
        "--timeout",
        type=float,
        default=120,
        help="seconds to wait for the app (default: 120)",
    )

    args = parser.parse_args()
    try:
        asyncio.run(_phone_uuid(args) if args.command == "phone-uuid" else _run(args))
    except LivewireError as e:
        sys.exit(f"Error: {e}")
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nAborted.")


if __name__ == "__main__":
    main()
