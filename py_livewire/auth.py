import asyncio
import base64
import json
from typing import Any

import aiohttp

from . import const
from .exceptions import ApiError, AuthenticationError


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
    the backend rejects it. The account UID is cached after the first login, so renewing
    a rejected token only re-requests a session token and the Gigya password login runs
    just once. This avoids hammering Gigya when the token expires: the password is only
    needed to obtain the UID, not to mint the token.
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
        self._uid: str | None = None
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
        # The UID is stable, so the Gigya password login only runs to obtain it the
        # first time; renewing an expired token re-requests a session token with it.
        if self._uid is None:
            self._uid = await self._gigya_uid(session)
        return await self._session_token(session, self._uid)

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

        error_code = res.get("errorCode", 0)
        if error_code != 0:
            message = f"Gigya login failed: {res.get('errorMessage')} ({error_code})"
            if error_code in const.GIGYA_CREDENTIAL_ERRORS:
                raise AuthenticationError(message)
            # A transient Gigya problem (rate limit, captcha, server error): retryable,
            # re-entering the credentials would not help.
            raise ApiError(message, code=str(error_code))
        if not res.get("UID"):
            raise ApiError("Gigya login returned no UID")

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
            # The session endpoint does not use the password, so a failure here is a
            # backend or transient problem, not a credential one: retryable, not reauth.
            raise ApiError(f"session request failed: {detail}", status=status)

        self.terms_accepted = res.get("termsAccepted")
        return str(res["jwt"])
