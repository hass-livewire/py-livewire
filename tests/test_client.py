import asyncio
import base64
import contextlib
import json
from collections.abc import Awaitable, Callable

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from py_livewire import (
    ApiError,
    AuthenticationError,
    Client,
    NotPairedError,
    PairingError,
)

DEVICE = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def make_jwt(sub: str, n: int) -> str:
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": sub, "n": n}).encode())
        .decode()
        .rstrip("=")
    )
    return f"eyJhbGciOiJIUzI1NiJ9.{payload}.c2ln"


class Backend:
    """Fake Gigya and LiveWire backend."""

    def __init__(self):
        self.sessions: list[dict] = []
        self.requests: list[tuple[web.Request, bytes]] = []
        self.handlers: dict[tuple[str, str], Handler] = {}
        self.next_token = make_jwt("user-1", 1)
        self.valid_token = self.next_token

    def route(self, method: str, path: str, data=None, status: int = 200) -> None:
        async def handler(request: web.Request) -> web.StreamResponse:
            if data is None:
                return web.Response(status=status)
            return web.json_response(data, status=status)

        self.handlers[(method, path)] = handler

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/accounts.login", self.gigya)
        app.router.add_post("/api/session", self.session)
        app.router.add_route("*", "/api/{path:.*}", self.api)
        return app

    async def gigya(self, request: web.Request) -> web.Response:
        form = await request.post()
        assert form["apiKey"] == "4_6aX8cf8RFVt6F3JQQZaF3A"
        if form["password"] != "secret":
            return web.json_response(
                {"errorCode": 403042, "errorMessage": "Invalid LoginID"}
            )
        return web.json_response({"errorCode": 0, "UID": "uid-1"})

    async def session(self, request: web.Request) -> web.Response:
        self.sessions.append(await request.json())
        self.valid_token = self.next_token
        return web.json_response({"jwt": self.valid_token, "termsAccepted": True})

    async def api(self, request: web.Request) -> web.StreamResponse:
        self.requests.append((request, await request.read()))
        if request.headers.get("Authorization") != f"Bearer {self.valid_token}":
            return web.Response(status=401)

        handler = self.handlers.get((request.method, request.match_info["path"]))
        return await handler(request) if handler else web.Response(status=404)


@contextlib.asynccontextmanager
async def serve(backend: Backend, password: str = "secret"):
    server = TestServer(backend.app())
    await server.start_server()
    base = str(server.make_url("")).rstrip("/")
    try:
        async with Client(
            "user@example.org", password, DEVICE, api_url=f"{base}/api", gigya_url=base
        ) as client:
            yield client
    finally:
        await server.close()


def run(test: Callable[[Client], Awaitable[None]], backend: Backend, **kwargs) -> None:
    async def main():
        async with serve(backend, **kwargs) as client:
            await test(client)

    asyncio.run(main())


BIKES = {
    "bikes": [
        {
            "id": "b1",
            "vin": "7TM3GDYD6SB000000",
            "model": "S2 Mulholland",
            "pairingStatus": True,
        }
    ]
}


def test_login_and_bikes():
    backend = Backend()
    backend.route("GET", "getAllbikes/pairingStatus", BIKES)

    async def test(client: Client):
        bikes = await client.get_bikes()
        assert [b.id for b in bikes] == ["b1"]
        assert bikes[0].paired
        assert client.user_id == "user-1"

    run(test, backend)

    assert backend.sessions == [
        {"UID": "uid-1", "deviceUUID": DEVICE, "dataCenter": "us1"}
    ]
    request, _ = backend.requests[0]
    assert request.query["brand"] == "LiveWire"
    assert request.query["deviceUUID"] == DEVICE
    assert request.headers["User-Agent"] == "Android"
    assert request.headers["model"] and request.headers["osVersion"]


def test_failed_login():
    async def test(client: Client):
        with pytest.raises(AuthenticationError, match="Invalid LoginID"):
            await client.login()

    run(test, Backend(), password="wrong")


def test_not_paired():
    backend = Backend()
    backend.route(
        "GET",
        "bikes/b1/charging/status",
        {"error": {"code": "3000", "description": "Command manager api failed"}},
    )

    async def test(client: Client):
        with pytest.raises(NotPairedError) as err:
            await client.get_charging_status("b1")
        assert err.value.code == "3000"

    run(test, backend)


def test_http_error():
    backend = Backend()
    backend.route(
        "GET",
        "bikes/b1/status/tpms",
        {"detail": "No static resource", "status": 404},
        status=404,
    )

    async def test(client: Client):
        with pytest.raises(ApiError, match="No static resource") as err:
            await client.get_tire_pressure("b1")
        assert err.value.status == 404

    run(test, backend)


def test_relogin_on_401():
    backend = Backend()
    backend.route("GET", "getAllbikes/pairingStatus", BIKES)

    async def test(client: Client):
        await client.login()
        # the backend expires the token, the next login yields a new one
        backend.valid_token = None
        backend.next_token = make_jwt("user-1", 2)

        assert len(await client.get_bikes()) == 1

    run(test, backend)
    assert len(backend.sessions) == 2


def test_pair():
    backend = Backend()
    backend.route("POST", "bikes/b1/pair", {"status": 200, "command_name": "pair"})
    backend.route("POST", "bikes/b1/verify/code", {"status": 200})

    states = iter([False, True])

    async def pairing_status(request: web.Request) -> web.Response:
        return web.json_response({"pairingStatus": next(states)})

    backend.handlers[("GET", "bikes/pairing/status/b1")] = pairing_status

    async def get_code() -> str:
        return " 123456 "

    async def test(client: Client):
        await client.pair("b1", get_code, interval=0)

    run(test, backend)

    calls = [(r.method, r.match_info["path"]) for r, _ in backend.requests]
    assert calls[:2] == [("POST", "bikes/b1/pair"), ("POST", "bikes/b1/verify/code")]
    request, body = backend.requests[1]
    assert request.query["deviceUUID"] == DEVICE
    assert json.loads(body) == {"code": "123456"}


@pytest.mark.parametrize(
    "response, match",
    [
        ({"code": 4004, "detail": "wrong"}, "wrong code"),
        ({"code": 4003}, "too many"),
    ],
)
def test_verify_rejected(response, match):
    backend = Backend()
    backend.route("POST", "bikes/b1/verify/code", response)

    async def test(client: Client):
        with pytest.raises(PairingError, match=match):
            await client.verify_pairing_code("b1", "000000")

    run(test, backend)


def test_pair_request_rejected():
    backend = Backend()
    backend.route("POST", "bikes/b1/pair", {"status": 402})

    async def test(client: Client):
        with pytest.raises(PairingError, match="cellular"):
            await client.request_pairing_code("b1")

    run(test, backend)


def test_query_encoding():
    backend = Backend()
    backend.route("GET", "rides", {"rides": [{"id": "r1"}]})
    backend.route(
        "POST", "ride", {"data": {"responseType": "SUCCESS", "ride": {"id": "r2"}}}
    )

    async def test(client: Client):
        rides = await client.get_rides(
            1.5, 2.5, sub_types=["HD", "DEALER"], tags=["tag=day-rides"]
        )
        assert rides == [{"id": "r1"}]
        assert await client.save_ride({"name": "Loop"}) == {
            "responseType": "SUCCESS",
            "ride": {"id": "r2"},
        }

    run(test, backend)

    request, _ = backend.requests[0]
    assert request.query.getall("subType") == ["HD", "DEALER"]
    assert request.query["tag"] == "tag=day-rides"
    assert request.query["includeLocationHistory"] == "false"
    assert "radiusInMiles" not in request.query

    request, body = backend.requests[1]
    assert request.query["bookmarkStatus"] == "false"
    assert "imported" not in request.query
    # the ride goes as JSON encoded string
    assert json.loads(json.loads(body)["ride"]) == {"name": "Loop"}


@pytest.mark.parametrize("status, deleted", [(204, True), (200, False)])
def test_delete_charging_schedule(status, deleted):
    backend = Backend()
    backend.route(
        "DELETE",
        "bikes/b1/charging/schedules/s1",
        None if status == 204 else {"status": "PENDING"},
        status,
    )

    async def test(client: Client):
        assert await client.delete_charging_schedule("b1", "s1") is deleted

    run(test, backend)


def test_invalid_device_uuid():
    with pytest.raises(ValueError):
        Client("user@example.org", "secret", "not-a-uuid")
