from __future__ import annotations

import json
import struct
import sys
from typing import Optional

from .blocklist_store import BlocklistStore


class NativeHost:
    def __init__(self) -> None:
        self.store = BlocklistStore()

    def run(self) -> None:
        while True:
            raw_length = sys.stdin.buffer.read(4)
            if not raw_length:
                break
            message_length = struct.unpack("<I", raw_length)[0]
            raw_message = sys.stdin.buffer.read(message_length)
            if not raw_message:
                break
            try:
                msg = json.loads(raw_message.decode("utf-8"))
            except json.JSONDecodeError:
                self._send({"type": "error", "message": "invalid_json"})
                continue
            self._handle(msg)

    def _handle(self, msg: dict) -> None:
        msg_type = msg.get("type")
        if msg_type == "request_state":
            self._send(self._state_payload())
        elif msg_type == "set_blocking":
            blocking = bool(msg.get("blocking", False))
            state = self.store.set_blocking(blocking)
            self._send(self._state_payload(state))
        elif msg_type == "set_domains":
            domains = list(msg.get("domains", []))
            state = self.store.set_domains(domains)
            self._send(self._state_payload(state))
        else:
            self._send({"type": "error", "message": "unknown_message"})

    def _state_payload(self, state=None) -> dict:
        if state is None:
            state = self.store.load()
        return {
            "type": "state",
            "blocking": state.blocking,
            "domains": state.domains,
            "version": state.version,
            "updated_at": state.updated_at,
        }

    def _send(self, msg: dict) -> None:
        raw = json.dumps(msg).encode("utf-8")
        sys.stdout.buffer.write(struct.pack("<I", len(raw)))
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()


def main() -> None:
    NativeHost().run()


if __name__ == "__main__":
    main()
