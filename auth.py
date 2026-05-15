"""Authentication helpers: personal bearer token or OAuth2 client-credentials."""

import time
from abc import ABC, abstractmethod

import requests


class AuthBase(ABC):
    @abstractmethod
    def get_token(self) -> str: ...


class PersonalTokenAuth(AuthBase):
    """Wraps a static bearer token (e.g. from developer.webex.com)."""

    def __init__(self, token: str):
        self._token = token.strip()

    def get_token(self) -> str:
        return self._token


class OAuthTokenManager(AuthBase):
    """Client-credentials OAuth2 for a Webex Service App. Auto-refreshes before expiry."""

    TOKEN_URL = "https://webexapis.com/v1/access_token"

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._access_token: str | None = None
        self._expiry: float = 0.0

    def get_token(self) -> str:
        if self._access_token and time.time() < self._expiry:
            return self._access_token
        return self._refresh()

    def _refresh(self) -> str:
        resp = requests.post(
            self.TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Token refresh failed ({resp.status_code}): {resp.text}"
            ) from exc

        data = resp.json()
        self._access_token = data["access_token"]
        # Subtract 2-minute buffer to refresh before actual expiry
        self._expiry = time.time() + data.get("expires_in", 43200) - 120
        return self._access_token


def build_auth(env: dict) -> AuthBase:
    """Pick the right auth strategy from environment variables.

    Prefers WXCC_BEARER_TOKEN if set; falls back to OAuth client credentials.
    """
    token = env.get("WXCC_BEARER_TOKEN", "").strip()
    if token:
        return PersonalTokenAuth(token)

    client_id = env.get("WXCC_CLIENT_ID", "").strip()
    client_secret = env.get("WXCC_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return OAuthTokenManager(client_id, client_secret)

    raise ValueError(
        "No authentication configured.\n"
        "Set WXCC_BEARER_TOKEN  — OR —  both WXCC_CLIENT_ID and WXCC_CLIENT_SECRET in your .env file."
    )
