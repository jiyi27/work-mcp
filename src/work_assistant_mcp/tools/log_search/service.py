from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiofiles

from ...config import LogSearchSettings
from ...hints import positive_int_param_hint, required_param_hint
from .strings import HINT_INVALID_SERVICE, HINT_NO_RESULTS, HINT_NO_SERVICES_CONFIGURED


class LogSearchService:
    def __init__(self, settings: LogSearchSettings) -> None:
        self._settings = settings

    async def list_services(self) -> dict[str, Any]:
        if not self._settings.services:
            return {
                "success": False,
                "error_type": "no_services_configured",
                "hint": HINT_NO_SERVICES_CONFIGURED,
            }

        services_info = []
        for service in self._settings.services:
            files = self._resolve_candidate_files(service)
            if files:
                latest = max(files, key=lambda p: p.stat().st_mtime)
                mtime = datetime.fromtimestamp(latest.stat().st_mtime)
                services_info.append({
                    "service": service,
                    "latest_file": latest.name,
                    "latest_mtime": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                })
            else:
                services_info.append({
                    "service": service,
                    "latest_file": None,
                    "latest_mtime": None,
                })
        return {"success": True, "services": services_info}

    async def search(self, service: str, query: str, limit: int = 100) -> dict[str, Any]:
        service = service.strip()
        query = query.strip()
        if not service:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("service"),
            }
        if not query:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": required_param_hint("query"),
            }
        if limit <= 0:
            return {
                "success": False,
                "error_type": "invalid_input",
                "hint": positive_int_param_hint("limit"),
            }
        if service not in self._settings.services:
            return {
                "success": False,
                "error_type": "invalid_service",
                "hint": HINT_INVALID_SERVICE,
            }

        files = self._resolve_candidate_files(service)
        tasks = [self._search_file(f, query, limit) for f in files]
        chunks = await asyncio.gather(*tasks)

        all_results: list[dict[str, Any]] = []
        for chunk in chunks:
            all_results.extend(chunk)

        all_results.sort(key=lambda e: e.get("time", ""), reverse=True)
        all_results = all_results[:limit]
        all_results.reverse()

        if not all_results:
            return {
                "success": True,
                "results": [],
                "hint": HINT_NO_RESULTS,
            }
        return {"success": True, "results": all_results}

    def _resolve_candidate_files(self, service: str) -> list[Path]:
        now = datetime.now()
        pattern = self._settings.file_pattern
        base = Path(self._settings.log_base_dir) / service

        time_slots = [now, now - timedelta(hours=1)] if "{H}" in pattern else [now]
        levels = list(self._settings.levels) if "{level}" in pattern else [""]

        seen: set[Path] = set()
        candidates: list[Path] = []
        for dt in time_slots:
            for level in levels:
                path = base / self._expand_pattern(pattern, dt, level)
                if path in seen:
                    continue
                seen.add(path)
                if path.exists():
                    candidates.append(path)

        return sorted(candidates, key=lambda p: p.stat().st_mtime)

    def _expand_pattern(self, pattern: str, dt: datetime, level: str) -> str:
        result = (
            pattern
            .replace("{Y}", dt.strftime("%Y"))
            .replace("{m}", dt.strftime("%m"))
            .replace("{d}", dt.strftime("%d"))
            .replace("{H}", dt.strftime("%H"))
        )
        if "{level}" in pattern:
            result = result.replace("{level}", level)
        return result

    async def _search_file(self, path: Path, query: str, limit: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            async with aiofiles.open(path, encoding="utf-8", errors="replace") as f:
                async for line in f:
                    if query not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    results.append(entry)
                    if len(results) >= limit:
                        break
        except OSError:
            pass
        return results
