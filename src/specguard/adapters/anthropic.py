"""AnthropicProvider — the live path.

If the key is missing or the call fails, this logs one line and hands over to
MockProvider. A dead key at 9 a.m. must not be able to break a review.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from .base import ModelError

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider:
    def __init__(self, model: str = "claude-sonnet-5", timeout: float = 60.0) -> None:
        self.model_id = model
        self.timeout = timeout
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise ModelError("ANTHROPIC_API_KEY is not set")

    def complete(self, system: str, user: str, *, max_tokens: int = 900) -> str:
        payload = {
            "model": self.model_id,
            "max_tokens": max_tokens,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        try:
            r = httpx.post(API_URL, json=payload, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # network, auth, rate limit — all the same to us
            raise ModelError(f"anthropic call failed: {exc}") from exc

        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise ModelError("anthropic returned an empty completion")
        return text
