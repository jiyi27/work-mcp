from __future__ import annotations

import base64
from typing import Any

from ...config import Settings
from ...http import HttpRequestError, request_bytes, request_json
from .models import JiraUser


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
        self._current_user_identifiers: frozenset[str] | None = None

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
        try:
            return request_json(
                method=method,
                url=f"{self._base_url}{path}",
                headers={
                    "Accept": "application/json",
                    "Authorization": self._auth_header(),
                },
                query=query,
                payload=payload,
                timeout=timeout,
                service_name="Jira",
            )
        except HttpRequestError as exc:
            raise JiraApiError(exc.message, status_code=exc.status_code) from exc

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

    def get_current_user_identifiers(self) -> frozenset[str]:
        if self._current_user_identifiers is not None:
            return self._current_user_identifiers

        payload = self._request(
            method="GET",
            path="/rest/api/2/myself",
        )
        user = JiraUser.from_api(payload)
        identifiers = user.identifiers()
        if not identifiers:
            raise JiraApiError("Jira myself response did not contain a usable user identity.")
        self._current_user_identifiers = identifiers
        return identifiers

    def download_attachment(self, url: str) -> bytes:
        try:
            return request_bytes(
                method="GET",
                url=url,
                headers={
                    "Accept": "*/*",
                    "Authorization": self._auth_header(),
                },
                timeout=JIRA_ATTACHMENT_TIMEOUT_SECONDS,
                service_name="Jira attachment download",
            )
        except HttpRequestError as exc:
            raise JiraApiError(exc.message, status_code=exc.status_code) from exc
