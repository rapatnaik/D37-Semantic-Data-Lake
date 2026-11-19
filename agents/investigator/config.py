"""Run settings from TOML plus credentials from the environment only.

Settings files are meant to be shared and saved into run manifests, so they
must never hold credentials. Any TOML key that looks like a credential is
rejected; the model API key is read from the environment variable named by
``model.api_key_env`` (default ``NRP_KEY``) at the moment it is needed.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CONFIG_NAME = "d37-agent.toml"
_CREDENTIAL_WORDS = ("key", "token", "secret", "password", "credential")
_ALLOWED_CREDENTIAL_KEYS = {"api_key_env"}  # names an env var; holds no secret


@dataclass(frozen=True)
class Limits:
    """Run-wide budgets. Defaults follow the team work split."""

    run_seconds: int = 15 * 60
    local_workers: int = 4
    custom_code_workers: int = 1
    concurrent_model_requests: int = 2
    model_requests_per_run: int = 30
    repair_attempts: int = 2
    tool_timeout_seconds: int = 300
    analysis_timeout_seconds: int = 120
    analysis_memory_mb: int = 1024
    analysis_cpus: float = 1.0
    analysis_pids: int = 128
    max_output_files: int = 50
    max_output_bytes: int = 50 * 1024 * 1024
    max_log_bytes: int = 1024 * 1024
    max_input_bytes: int = 2 * 1024 * 1024 * 1024
    followup_steps: int = 8

    def check(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"limits.{item.name} must be a nonnegative number")
        if self.local_workers < 1:
            raise ValueError("limits.local_workers must be at least 1")
        if self.custom_code_workers not in (0, 1):
            raise ValueError("limits.custom_code_workers must be 0 or 1")
        if self.custom_code_workers > self.local_workers:
            raise ValueError("custom-code workers count toward local_workers")
        if self.concurrent_model_requests < 1:
            raise ValueError("limits.concurrent_model_requests must be at least 1")
        if self.repair_attempts > 2:
            raise ValueError("limits.repair_attempts may not exceed 2")


@dataclass(frozen=True)
class ModelSettings:
    endpoint: str = "https://ellm.nrp-nautilus.io/v1/chat/completions"
    name: str = "gpt-oss"
    api_key_env: str = "NRP_KEY"
    enabled: bool = True


@dataclass(frozen=True)
class ExecutionSettings:
    # "docker" isolates network, credentials, and resources. "process" is a
    # development fallback: no credentials and rlimits, but network is open.
    backend: str = "docker"
    image: str = "d37-investigator-worker:latest"
    docker_command: str = "docker"
    tool_isolation: str = "process"  # "process" (killable) or "inline" (debugging)

    def check(self) -> None:
        if self.backend not in {"docker", "process"}:
            raise ValueError("execution.backend must be 'docker' or 'process'")
        if self.tool_isolation not in {"process", "inline"}:
            raise ValueError("execution.tool_isolation must be 'process' or 'inline'")


@dataclass(frozen=True)
class Config:
    limits: Limits = field(default_factory=Limits)
    model: ModelSettings = field(default_factory=ModelSettings)
    execution: ExecutionSettings = field(default_factory=ExecutionSettings)
    seed: int = 0
    hash_inputs: bool = True
    state_dir: str | None = None  # default: <dataset_root>/.d37-agent

    def check(self) -> None:
        self.limits.check()
        self.execution.check()
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")

    def public_dict(self) -> dict[str, Any]:
        """Settings safe to save in manifests: credentials are never fields."""
        return asdict(self)

    def api_key(self, environ: Mapping[str, str] | None = None) -> str | None:
        environ = os.environ if environ is None else environ
        value = environ.get(self.model.api_key_env, "").strip()
        return value or None


_SECTIONS = {"limits": Limits, "model": ModelSettings, "execution": ExecutionSettings}


def _reject_credentials(data: Mapping[str, Any], prefix: str = "") -> None:
    for key, value in data.items():
        lower = key.lower()
        if lower not in _ALLOWED_CREDENTIAL_KEYS and any(word in lower for word in _CREDENTIAL_WORDS):
            raise ValueError(
                f"Settings may not contain credentials ({prefix}{key}); "
                "set them in the environment instead"
            )
        if isinstance(value, Mapping):
            _reject_credentials(value, f"{prefix}{key}.")


def _section(cls: type, data: Any, name: str) -> Any:
    if not isinstance(data, Mapping):
        raise ValueError(f"[{name}] must be a table")
    known = {item.name: item for item in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"Unknown settings in [{name}]: {sorted(unknown)}")
    defaults = cls()
    for key, value in data.items():
        expected = type(getattr(defaults, key))
        ok = isinstance(value, expected) and not (expected is int and isinstance(value, bool))
        if expected is float and isinstance(value, int) and not isinstance(value, bool):
            ok = True
        if not ok:
            raise ValueError(f"{name}.{key} must be {expected.__name__}")
    return cls(**data)


def config_from_dict(data: Mapping[str, Any]) -> Config:
    _reject_credentials(data)
    top = {item.name for item in fields(Config)}
    unknown = set(data) - top
    if unknown:
        raise ValueError(f"Unknown settings: {sorted(unknown)}")
    values: dict[str, Any] = {}
    for key, value in data.items():
        if key in _SECTIONS:
            values[key] = _section(_SECTIONS[key], value, key)
        elif key == "seed":
            values[key] = value
        elif key == "hash_inputs":
            if not isinstance(value, bool):
                raise ValueError("hash_inputs must be true or false")
            values[key] = value
        elif key == "state_dir":
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("state_dir must be a nonempty string")
            values[key] = value
    config = Config(**values)
    config.check()
    return config


def load_config(path: str | Path | None = None, *, search_dir: str | Path | None = None) -> Config:
    """Load ``path``, or ``<search_dir>/d37-agent.toml`` if present, else defaults."""
    if path is None and search_dir is not None:
        candidate = Path(search_dir) / DEFAULT_CONFIG_NAME
        path = candidate if candidate.is_file() else None
    if path is None:
        config = Config()
        config.check()
        return config
    with Path(path).open("rb") as handle:
        return config_from_dict(tomllib.load(handle))


def with_overrides(config: Config, **sections: Mapping[str, Any]) -> Config:
    """Apply CLI overrides such as ``execution={'backend': 'process'}``."""
    updated = config
    for name, values in sections.items():
        if values:
            updated = replace(updated, **{name: replace(getattr(updated, name), **values)})
    updated.check()
    return updated


def redact(text: str, config: Config | None = None, environ: Mapping[str, str] | None = None) -> str:
    """Remove credential values that might have leaked into logs or messages."""
    environ = os.environ if environ is None else environ
    names = {(config or Config()).model.api_key_env, "NRP_KEY"}
    names.update(
        key for key in environ
        if any(word in key.lower() for word in _CREDENTIAL_WORDS)
    )
    for name in names:
        value = environ.get(name, "")
        if len(value) >= 6:
            text = text.replace(value, f"<redacted:{name}>")
    return text
