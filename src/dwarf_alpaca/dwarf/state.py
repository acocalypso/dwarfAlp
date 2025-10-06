from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ConnectivityState:
    sta_ip: Optional[str] = None
    last_error: Optional[str] = None
    mode: str = "unknown"
    wifi_credentials: dict[str, str] = field(default_factory=dict)


@dataclass
class StateStore:
    path: Path
    state: ConnectivityState = field(default_factory=ConnectivityState)

    def load(self) -> ConnectivityState:
        if not self.path.exists():
            return self.state

        try:
            with self.path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except json.JSONDecodeError:
            return self.state

        self.state = ConnectivityState(**data)
        return self.state

    def save(self, state: ConnectivityState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as stream:
            json.dump(state.__dict__, stream, indent=2)
        self.state = state

    def record_error(self, message: str) -> ConnectivityState:
        self.state.last_error = message
        self.save(self.state)
        return self.state
