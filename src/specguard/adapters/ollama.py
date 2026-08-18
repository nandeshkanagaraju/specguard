"""OllamaProvider — a local model, for running the live path without a network."""

from __future__ import annotations

import httpx

from .base import ModelError


class OllamaProvider:
    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        host: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self.model_id = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def complete(self, system: str, user: str, *, max_tokens: int = 900) -> str:
        payload = {
            "model": self.model_id,
            "system": system,
            "prompt": user,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "seed": 7, "num_predict": max_tokens},
        }
        try:
            r = httpx.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            raise ModelError(f"ollama call failed: {exc}") from exc

        text = (data.get("response") or "").strip()
        if not text:
            raise ModelError("ollama returned an empty completion")
        return text
