import asyncio
import base64
import json
from typing import Any

import aiohttp

from . import const
from .exceptions import AuthenticationError


def jwt_subject(token: str) -> str | None:
    """Return the "sub" claim of the session token, which is the backend's user UUID."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
    except (IndexError, ValueError):
        return None
    return claims.get("sub") if isinstance(claims, dict) else None


class Authenticator:
    """Logs in to Gigya and exchanges the account UID for a LiveWire session token.

    The token carries no usable expiry and there is no refresh flow, so it is used until
    the backend rejects it, which triggers a full login again.
    """

    def __init__(
        self,
        email: str,
        password: str,
        device_uuid: str,
        headers: dict[str, str],
        *,
        gigya_url: str,
        api_url: str,
    ):
        self._email = email
        self._password = password
        self._device_uuid = device_uuid
        self._headers = headers
        self._gigya_url = gigya_url
        self._api_url = api_url

        self._token: str | None = None
        self._lock = asyncio.Lock()
        self.terms_accepted: bool | None = None

    @property
    def token(self) -> str | None:
        return self._token

    async def get_token(self, session: aiohttp.ClientSession) -> str:
        async with self._lock:
            if self._token is None:
                self._token = await self._login(session)
            return self._token

    async def refresh(self, session: aiohttp.ClientSession, rejected: str) -> str:
        """Log in again, unless a concurrent request already replaced the token."""
        async with self._lock:
            if self._token in (None, rejected):
                self._token = await self._login(session)
            return self._token

    async def _login(self, session: aiohttp.ClientSession) -> str:
        uid = await self._gigya_uid(session)
        return await self._session_token(session, uid)

    async def _gigya_uid(self, session: aiohttp.ClientSession) -> str:
        # Gigya expects a form and reports errors in a body with HTTP 200
        async with session.post(
            f"{self._gigya_url}/accounts.login",
            data={
                "apiKey": const.GIGYA_API_KEY,
                "loginID": self._email,
                "password": self._password,
                "include": "profile,data",
                "format": "json",
            },
        ) as resp:
            res: dict[str, Any] = await resp.json(content_type=None)

        if res.get("errorCode", 0) != 0:
            raise AuthenticationError(
                f"Gigya login failed: {res.get('errorMessage')} "
                f"({res.get('errorCode')})"
            )
        if not res.get("UID"):
            raise AuthenticationError("Gigya login returned no UID")

        return str(res["UID"])

    async def _session_token(self, session: aiohttp.ClientSession, uid: str) -> str:
        async with session.post(
            f"{self._api_url}/session",
            params={"brand": const.BRAND},
            json={
                "UID": uid,
                "deviceUUID": self._device_uuid,
                "dataCenter": const.DATA_CENTER,
            },
            headers=self._headers,
        ) as resp:
            status = resp.status
            res = await resp.json(content_type=None)

        if not isinstance(res, dict):
            res = {}
        if not res.get("jwt"):
            detail = (res.get("error") or {}).get("description") or f"HTTP {status}"
            raise AuthenticationError(f"session request failed: {detail}")

        self.terms_accepted = res.get("termsAccepted")
        return str(res["jwt"])
