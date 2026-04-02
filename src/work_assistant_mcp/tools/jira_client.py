from __future__ import annotations

import base64
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import Settings


JIRA_TIMEOUT_SECONDS = 30
JIRA_ATTACHMENT_TIMEOUT_SECONDS = 60


class JiraApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class JiraClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = self._require(settings.jira_base_url, "JIRA_BASE_URL")
        self._email = self._require(settings.jira_email, "JIRA_EMAIL")
        self._api_token = self._require(settings.jira_api_token, "JIRA_API_TOKEN")

    @staticmethod
    def _require(value: str | None, env_name: str) -> str:
        if value:
            return value.rstrip("/")
        raise RuntimeError(f"Missing {env_name}. Configure it in the environment or .env.")

    def _auth_header(self) -> str:
        raw = f"{self._email}:{self._api_token}".encode("utf-8")
        return f"Basic {base64.b64encode(raw).decode('ascii')}"

    def _request(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: int = JIRA_TIMEOUT_SECONDS,
    ) -> Any:
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": self._auth_header(),
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise JiraApiError(
                f"Jira request failed with HTTP {exc.code}: {error_body}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise JiraApiError(f"Failed to reach Jira: {exc.reason}") from exc

        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise JiraApiError("Jira returned invalid JSON.") from exc

    def search_issues(self, *, jql: str, fields: tuple[str, ...], max_results: int) -> list[dict[str, Any]]:
        payload = self._request(
            method="GET",
            path="/rest/api/2/search",
            query={
                "jql": jql,
                "fields": ",".join(fields),
                "maxResults": max_results,
            },
        )
        issues = payload.get("issues") if isinstance(payload, dict) else None
        if not isinstance(issues, list):
            raise JiraApiError("Jira search response did not contain an issues list.")
        return [item for item in issues if isinstance(item, dict)]

    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        payload = self._request(
            method="GET",
            path=f"/rest/api/2/issue/{issue_key}/transitions",
        )
        transitions = payload.get("transitions") if isinstance(payload, dict) else None
        if not isinstance(transitions, list):
            raise JiraApiError("Jira transitions response did not contain a transitions list.")
        return [item for item in transitions if isinstance(item, dict)]

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self._request(
            method="POST",
            path=f"/rest/api/2/issue/{issue_key}/transitions",
            payload={"transition": {"id": transition_id}},
        )

    def download_attachment(self, url: str) -> bytes:
        request = Request(
            url,
            headers={
                "Accept": "*/*",
                "Authorization": self._auth_header(),
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=JIRA_ATTACHMENT_TIMEOUT_SECONDS) as response:
                return response.read()
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise JiraApiError(
                f"Jira attachment download failed with HTTP {exc.code}: {error_body}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise JiraApiError(f"Failed to download Jira attachment: {exc.reason}") from exc
