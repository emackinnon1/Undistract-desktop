from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List

APP_DIR = Path.home() / "Library" / "Application Support" / "Undistract"
STATE_FILE = APP_DIR / "state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BlockState:
    blocking: bool = False
    domains: List[str] = field(default_factory=list)
    version: int = 0
    updated_at: str = field(default_factory=_now_iso)


class BlocklistStore:
    def __init__(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        if not STATE_FILE.exists():
            self.save(BlockState())

    def load(self) -> BlockState:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return BlockState(
            blocking=bool(data.get("blocking", False)),
            domains=list(data.get("domains", [])),
            version=int(data.get("version", 0)),
            updated_at=str(data.get("updated_at", _now_iso())),
        )

    def save(self, state: BlockState) -> None:
        state.updated_at = _now_iso()
        state.version = max(0, int(state.version))
        normalized_domains = sorted({d.strip().lower() for d in state.domains if d.strip()})
        state.domains = normalized_domains
        payload = {
            "blocking": state.blocking,
            "domains": normalized_domains,
            "version": state.version,
            "updated_at": state.updated_at,
        }
        tmp_file = STATE_FILE.with_suffix(".tmp")
        with tmp_file.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_file, STATE_FILE)

    def set_blocking(self, blocking: bool) -> BlockState:
        state = self.load()
        state.blocking = blocking
        state.version += 1
        self.save(state)
        return state

    def set_domains(self, domains: List[str]) -> BlockState:
        state = self.load()
        state.domains = domains
        state.version += 1
        self.save(state)
        return state
