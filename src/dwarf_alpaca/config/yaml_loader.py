from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel
import yaml

from .settings import Settings


def load_yaml_settings(base_settings: Settings, config_path: str | Path) -> Settings:
    """Overlay settings from a YAML file onto the base `Settings` instance."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}

    merged = base_settings.model_dump()
    for key, value in data.items():
        merged[key] = value

    return Settings(**merged)
