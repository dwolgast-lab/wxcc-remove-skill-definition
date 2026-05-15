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

    def _url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"

    def _org(self, path: str) -> str:
        return f"organization/{self.org_id}/{path.lstrip('/')}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._auth.get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = self._url(path)
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
            for key in ("data", "dataList", "items", "records", "results", "content", "value"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    def _get_all(self, path: str, extra_params: dict | None = None) -> list:
        """Fetch every page and return a flat list."""
        results: list = []
        page = 0
        while True:
            params = dict(extra_params or {})
            params.update({"page": page, "pageSize": self.PAGE_SIZE})
            data = self._request("GET", path, params=params)
            batch = self._items(data)
            results.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
            page += 1
        return results

    # ------------------------------------------------------------------
    # Skill Definitions  —  /organization/{orgId}/skill
    # ------------------------------------------------------------------

    def get_skill_definitions(self) -> list[dict]:
        return self._get_all(self._org("skill"))

    def delete_skill_definition(self, skill_id: str) -> None:
        self._request("DELETE", self._org(f"skill/{skill_id}"))

    def find_skill(self, name_or_id: str) -> dict | None:
        """Resolve a skill by exact ID or case-insensitive name."""
        needle = name_or_id.strip()
        needle_lower = needle.lower()
        for skill in self.get_skill_definitions():
            if skill.get("id") == needle or skill.get("name", "").lower() == needle_lower:
                return skill
        return None

    def get_skill_references(self, skill_id: str) -> list[dict]:
        """Return all objects that reference this skill, each tagged with '_entity_type'.

        The incoming-references API returns refs grouped by entity type, with the
        type stored in meta.currentEntity rather than on individual items.  Multiple
        entity types may require separate paginated calls.
        """
        base = self._org(f"skill/{skill_id}/incoming-references")
        all_refs: list[dict] = []
        seen: set[str] = set()

        def _collect(entity_type: str | None, page: int) -> dict | None:
            params: dict = {"page": page, "pageSize": self.PAGE_SIZE}
            if entity_type:
                params["currentEntity"] = entity_type
            try:
                return self._request("GET", base, params=params)
            except WxCCAPIError:
                return None

        def _process_response(resp: dict) -> tuple[str, int]:
            """Tag items with their entity type; return (entity_type, total_pages)."""
            meta = resp.get("meta", {})
            etype = meta.get("currentEntity", "unknown")
            total = meta.get("totalPages", 1)
            for ref in resp.get("data", []):
                ref["_entity_type"] = etype
                all_refs.append(ref)
            return etype, total

        # First call — reveals which entity types have references
        resp = _collect(None, 0)
        if not resp:
            return []

        meta = resp.get("meta", {})
        referenced_entities: list[str] = meta.get("referencedEntities", [])
        etype, total_pages = _process_response(resp)
        seen.add(etype)

        for page in range(1, total_pages):
            r = _collect(etype, page)
            if r:
                _process_response(r)

        # Collect any remaining entity types
        for et in referenced_entities:
            if et in seen:
                continue
            page = 0
            while True:
                r = _collect(et, page)
                if not r:
                    break
                _, tp = _process_response(r)
                seen.add(et)
                page += 1
                if page >= tp:
                    break

        return all_refs

    # ------------------------------------------------------------------
    # Skill Profiles  —  /organization/{orgId}/v2/skill-profile
    # ------------------------------------------------------------------

    def get_skill_profile(self, profile_id: str) -> dict:
        return self._request(
            "GET",
            self._org(f"skill-profile/{profile_id}"),
            params={"includeSkillDetails": ""},
        )

    def update_skill_profile(self, profile_id: str, data: dict) -> dict:
        return self._request(
            "PUT",
            self._org(f"skill-profile/{profile_id}"),
            params={"skillProfileDTO": ""},
            json=data,
        )

    # ------------------------------------------------------------------
    # Queues  —  /organization/{orgId}/v2/contact-service-queue
    # ------------------------------------------------------------------

    def get_queue(self, queue_id: str) -> dict:
        return self._request("GET", self._org(f"v2/contact-service-queue/{queue_id}"))

    def update_queue(self, queue_id: str, data: dict) -> dict:
        return self._request("PUT", self._org(f"v2/contact-service-queue/{queue_id}"), json=data)
