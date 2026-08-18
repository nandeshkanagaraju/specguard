"""Model backends. Selection lives here so the engine never imports a provider."""

from __future__ import annotations

import sys
from pathlib import Path

from ..config import Config
from .base import ModelAdapter, ModelError, parse_json_response
from .mock import MockProvider

__all__ = [
    "ModelAdapter",
    "ModelError",
    "MockProvider",
    "parse_json_response",
    "build_adapter",
]


def build_adapter(cfg: Config, provider: str | None = None, *, delay: bool = True) -> ModelAdapter:
    """Resolve the configured provider, falling back to the mock if it cannot run."""
    name = (provider or cfg.model.provider or "mock").lower()

    if name == "anthropic":
        try:
            from .anthropic import AnthropicProvider

            return AnthropicProvider(model=cfg.model.anthropic_model)
        except ModelError as exc:
            print(f"specguard: {exc}; falling back to the mock provider", file=sys.stderr)
            return MockProvider(cfg.root, delay=delay)

    if name == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(model=cfg.model.ollama_model, host=cfg.model.ollama_host)

    return MockProvider(cfg.root, delay=delay)
