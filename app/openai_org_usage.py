"""
Fetch aggregated completion token usage from OpenAI's organization Usage API.

Requires an Admin API key (not the same as a standard project API key):
https://platform.openai.com/settings/organization/admin-keys

Set OPENAI_ADMIN_API_KEY in the environment. This always calls https://api.openai.com/v1
(regardless of OPENAI_BASE_URL used for chat — e.g. Gemini proxy).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OPENAI_USAGE_URL = "https://api.openai.com/v1/organization/usage/completions"


def _start_of_utc_day_ts() -> int:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


def fetch_completions_tokens_today_utc(admin_api_key: str) -> tuple[int, Optional[str]]:
    """
    Sum input_tokens + output_tokens for the current UTC calendar day (from buckets).

    Returns (total_tokens, error_message). error_message is set on failure.
    """
    if not admin_api_key.strip():
        return 0, "Missing OPENAI_ADMIN_API_KEY"

    start_ts = _start_of_utc_day_ts()
    end_ts = int(datetime.now(timezone.utc).timestamp())

    total_in = 0
    total_out = 0
    page_cursor: str | None = None

    while True:
        params: dict = {
            "start_time": start_ts,
            "end_time": end_ts,
            "bucket_width": "1h",
        }
        if page_cursor:
            params["page"] = page_cursor

        url = f"{OPENAI_USAGE_URL}?{urlencode(params)}"
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {admin_api_key.strip()}",
                "Content-Type": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=45) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            return 0, f"HTTP {e.code}: {body or e.reason}"
        except URLError as e:
            return 0, str(e.reason if hasattr(e, "reason") else e)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            return 0, f"Invalid JSON: {e}"

        for bucket in payload.get("data") or []:
            for res in bucket.get("results") or []:
                total_in += int(res.get("input_tokens") or 0)
                total_out += int(res.get("output_tokens") or 0)

        page_cursor = payload.get("next_page")
        if not page_cursor:
            break

    return total_in + total_out, None


def should_use_openai_org_usage() -> bool:
    if os.environ.get("OPENAI_ORG_USAGE", "auto").lower() == "0":
        return False
    if not (os.environ.get("OPENAI_ADMIN_API_KEY") or "").strip():
        return False
    mode = os.environ.get("OPENAI_ORG_USAGE", "auto").lower()
    if mode == "force" or mode == "1" or mode == "true":
        return True
    # auto: only if chat is pointed at OpenAI (avoid misleading zeros for Gemini-only)
    base = (os.environ.get("OPENAI_BASE_URL") or "").lower()
    if not base or "openai.com" in base or "api.openai.com" in base:
        return True
    return False
