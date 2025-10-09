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

        if not isinstance(data, dict):
            return self.state

        data.setdefault("sta_ip", None)
        data.setdefault("last_error", None)
        data.setdefault("mode", "unknown")
        raw_credentials = data.get("wifi_credentials", {})
        if isinstance(raw_credentials, dict):
            sanitized_credentials: dict[str, str] = {}
            for ssid, password in raw_credentials.items():
                if isinstance(ssid, str) and isinstance(password, str) and password:
                    sanitized_credentials[ssid] = password
            data["wifi_credentials"] = sanitized_credentials
        else:
            data["wifi_credentials"] = {}

        self.state = ConnectivityState(**data)
        return self.state

    def save(self, state: ConnectivityState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sanitized = ConnectivityState(
            sta_ip=state.sta_ip,
            last_error=state.last_error,
            mode=state.mode,
            wifi_credentials={
                ssid: password
                for ssid, password in state.wifi_credentials.items()
                if isinstance(ssid, str) and isinstance(password, str) and password
            },
        )
        with self.path.open("w", encoding="utf-8") as stream:
            json.dump(sanitized.__dict__, stream, indent=2)
        self.state = sanitized

    def record_error(self, message: str) -> ConnectivityState:
        self.state.last_error = message
        self.save(self.state)
        return self.state
