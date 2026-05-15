"""WxCC REST API client with pagination and retry on rate-limit."""

import time
from typing import Any

import requests

from auth import AuthBase

VALID_REGIONS = ("us1", "us2", "eu1", "eu2", "anz1", "jp1", "ca1", "in1")


class WxCCAPIError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {body}")


class WxCCClient:
    PAGE_SIZE = 200
    MAX_RETRIES = 3

    def __init__(self, org_id: str, auth: AuthBase, region: str = "us1"):
        self.org_id = org_id
        self._auth = auth
        self._base = f"https://api.wxcc-{region}.cisco.com"
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _url(self, resource: str) -> str:
        return f"{self._base}/organization/{self.org_id}/{resource.lstrip('/')}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._auth.get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, resource: str, **kwargs) -> Any:
        url = self._url(resource)
        for attempt in range(self.MAX_RETRIES):
            resp = self._session.request(method, url, headers=self._headers(), timeout=30, **kwargs)

            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
                time.sleep(wait)
                continue

            if resp.status_code == 204:
                return None

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                raise WxCCAPIError(resp.status_code, resp.text) from exc

            return resp.json() if resp.content else None

        raise WxCCAPIError(429, "Still rate-limited after retries")

    @staticmethod
    def _items(data: Any) -> list:
        """Normalise varied WxCC list response shapes to a plain list."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "dataList", "items", "records", "results", "content"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    def _get_all(self, resource: str, extra_params: dict | None = None) -> list:
        """Fetch every page and return a flat list."""
        results: list = []
        page = 0
        while True:
            params = dict(extra_params or {})
            params.update({"page": page, "pageSize": self.PAGE_SIZE})
            data = self._request("GET", resource, params=params)
            batch = self._items(data)
            results.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
            page += 1
        return results

    # ------------------------------------------------------------------
    # Skill Definitions
    # ------------------------------------------------------------------

    def get_skill_definitions(self) -> list[dict]:
        return self._get_all("skill-definition")

    def get_skill_definition(self, skill_id: str) -> dict:
        return self._request("GET", f"skill-definition/{skill_id}")

    def delete_skill_definition(self, skill_id: str) -> None:
        self._request("DELETE", f"skill-definition/{skill_id}")

    def find_skill(self, name_or_id: str) -> dict | None:
        """Resolve a skill by exact ID or case-insensitive name."""
        needle = name_or_id.strip()
        needle_lower = needle.lower()
        for skill in self.get_skill_definitions():
            if skill.get("id") == needle or skill.get("name", "").lower() == needle_lower:
                return skill
        return None

    # ------------------------------------------------------------------
    # Skill Profiles
    # ------------------------------------------------------------------

    def get_skill_profiles(self) -> list[dict]:
        return self._get_all("skill-profile")

    def get_skill_profile(self, profile_id: str) -> dict:
        return self._request("GET", f"skill-profile/{profile_id}")

    def update_skill_profile(self, profile_id: str, data: dict) -> dict:
        return self._request("PUT", f"skill-profile/{profile_id}", json=data)

    # ------------------------------------------------------------------
    # Queues
    # ------------------------------------------------------------------

    def get_queues(self) -> list[dict]:
        return self._get_all("queue")

    def get_queue(self, queue_id: str) -> dict:
        return self._request("GET", f"queue/{queue_id}")

    def update_queue(self, queue_id: str, data: dict) -> dict:
        return self._request("PUT", f"queue/{queue_id}", json=data)

    # ------------------------------------------------------------------
    # Flows
    # ------------------------------------------------------------------

    def get_flows(self) -> list[dict]:
        try:
            return self._get_all("flow")
        except WxCCAPIError:
            # Flow API may require elevated scopes or be unavailable in some tenants
            return []

    def get_flow(self, flow_id: str) -> dict:
        return self._request("GET", f"flow/{flow_id}")
