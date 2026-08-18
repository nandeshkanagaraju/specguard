"""specguard.toml loading. Thresholds live here so they are visibly policy, not magic numbers."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TOML = """\
# SpecGuard configuration

[spec]
path = "SPEC.md"

[model]
provider = "mock"            # mock | anthropic | ollama
anthropic_model = "claude-sonnet-5"
ollama_model = "qwen2.5-coder:7b"
ollama_host = "http://localhost:11434"

[retrieval]
top_k = 3
floor = 0.15

[scoring]
# Below this, the verdict is downgraded to NEEDS_HUMAN. This is a policy knob,
# not a constant of nature: raise it to abstain more, lower it to decide more.
abstain_below = 0.55

[report]
strict = false               # when true, NEEDS_HUMAN / UNMAPPED also fail the build
"""


@dataclass
class ModelConfig:
    provider: str = "mock"
    anthropic_model: str = "claude-sonnet-5"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_host: str = "http://localhost:11434"


@dataclass
class Config:
    root: Path = field(default_factory=Path.cwd)
    spec_path: str = "SPEC.md"
    model: ModelConfig = field(default_factory=ModelConfig)
    top_k: int = 3
    floor: float = 0.15
    abstain_below: float = 0.55
    strict: bool = False

    @property
    def workdir(self) -> Path:
        return self.root / ".specguard"

    @property
    def cache_dir(self) -> Path:
        return self.workdir / "cache"

    @property
    def report_path(self) -> Path:
        return self.workdir / "report.json"


def load_config(root: Path) -> Config:
    root = Path(root).resolve()
    cfg = Config(root=root)
    toml_path = root / "specguard.toml"
    if not toml_path.exists():
        return cfg
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    spec = data.get("spec", {})
    cfg.spec_path = spec.get("path", cfg.spec_path)

    m = data.get("model", {})
    cfg.model = ModelConfig(
        provider=m.get("provider", "mock"),
        anthropic_model=m.get("anthropic_model", ModelConfig.anthropic_model),
        ollama_model=m.get("ollama_model", ModelConfig.ollama_model),
        ollama_host=m.get("ollama_host", ModelConfig.ollama_host),
    )

    r = data.get("retrieval", {})
    cfg.top_k = int(r.get("top_k", cfg.top_k))
    cfg.floor = float(r.get("floor", cfg.floor))

    s = data.get("scoring", {})
    cfg.abstain_below = float(s.get("abstain_below", cfg.abstain_below))

    rep = data.get("report", {})
    cfg.strict = bool(rep.get("strict", cfg.strict))
    return cfg
