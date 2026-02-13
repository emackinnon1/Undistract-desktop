from __future__ import annotations

import json
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from .blocklist_store import BlocklistStore, STATE_FILE


class NativeHost:
    def __init__(self) -> None:
        self.store = BlocklistStore()
        self._last_version = self.store.load().version
        self._stop_event = threading.Event()
        self._watcher_thread: Optional[threading.Thread] = None

    def run(self) -> None:
        # Start file watcher in background thread
        self._watcher_thread = threading.Thread(target=self._watch_state_file, daemon=True)
        self._watcher_thread.start()
        
        # Main message loop
        while True:
            raw_length = sys.stdin.buffer.read(4)
            if not raw_length:
                self._stop_event.set()
                break
            message_length = struct.unpack("<I", raw_length)[0]
            raw_message = sys.stdin.buffer.read(message_length)
            if not raw_message:
                self._stop_event.set()
                break
            try:
                msg = json.loads(raw_message.decode("utf-8"))
            except json.JSONDecodeError:
                self._send({"type": "error", "message": "invalid_json"})
                continue
            self._handle(msg)

    def _watch_state_file(self) -> None:
        """Poll the state file and push updates when version changes."""
        while not self._stop_event.is_set():
            time.sleep(0.5)  # Check every 500ms
            try:
                state = self.store.load()
                if state.version != self._last_version:
                    self._last_version = state.version
                    self._send(self._state_payload(state))
            except Exception:
                # Ignore read errors, keep watching
                pass

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
