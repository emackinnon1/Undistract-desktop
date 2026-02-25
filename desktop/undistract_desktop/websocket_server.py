from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing as mp
import multiprocessing.synchronize
import queue
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

from .blocklist_store import BlocklistStore
from .ble_worker import run_ble_worker

logger = logging.getLogger(__name__)


DEFAULT_BLE_SERVICE_UUID = "a4f7e000-0000-1000-8000-00805f9b34fb"
DEFAULT_BLE_CHAR_UUID = "a4f7e001-0000-1000-8000-00805f9b34fb"


@dataclass
class ClientState:
    authed: bool = False


class BleToggleClient:
    """Manages BLE connection to the mobile app via a child subprocess.

    Running BLE in a separate process ensures each restart gets a
    completely fresh CoreBluetooth context — the only reliable way to
    recover from macOS sleep/wake BLE connection issues.
    """

    def __init__(
        self,
        on_toggle,
        service_uuid: str = DEFAULT_BLE_SERVICE_UUID,
        char_uuid: str = DEFAULT_BLE_CHAR_UUID,
        device_name: Optional[str] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_devices: Optional[Callable[[List[str]], None]] = None,
        on_connected: Optional[Callable[[bool], None]] = None,
        log_queue: Optional[mp.Queue] = None,
    ) -> None:
        self._on_toggle = on_toggle
        self._service_uuid = service_uuid.lower()
        self._char_uuid = char_uuid
        self._device_name = device_name
        self._on_status = on_status
        self._on_devices = on_devices
        self._on_connected = on_connected
        self._stop_event = asyncio.Event()
        self._mp_stop: Optional[multiprocessing.synchronize.Event] = None
        self._log_queue = log_queue

    async def stop(self) -> None:
        self._stop_event.set()
        if self._mp_stop is not None:
            self._mp_stop.set()

    # ------------------------------------------------------------------
    # Subprocess lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Spawn and supervise a BLE worker subprocess.

        When the subprocess exits (sleep detected, CoreBluetooth stuck,
        or normal disconnect), a fresh subprocess is spawned — giving it
        a clean CoreBluetooth context identical to an app restart.
        """
        logger.info("BLE client starting (subprocess mode)")

        while not self._stop_event.is_set():
            event_queue: mp.Queue = mp.Queue()
            mp_stop = mp.Event()
            self._mp_stop = mp_stop

            process = mp.Process(
                target=run_ble_worker,
                args=(
                    event_queue,
                    mp_stop,
                    self._log_queue,
                    self._service_uuid,
                    self._char_uuid,
                    self._device_name,
                ),
                daemon=True,
            )
            process.start()
            logger.info("BLE subprocess started (pid=%d)", process.pid)
            self._emit_status("BLE: subprocess started")

            try:
                await self._consume_events(event_queue, process)
            except Exception as exc:
                logger.error(
                    "Error in subprocess event loop: %s", exc, exc_info=True,
                )
            finally:
                mp_stop.set()
                process.join(timeout=5)
                if process.is_alive():
                    logger.warning("Killing unresponsive BLE subprocess")
                    process.kill()
                    process.join(timeout=2)
                logger.info("BLE subprocess terminated")
                # Ensure the multiprocessing.Queue is properly cleaned up
                event_queue.close()
                event_queue.join_thread()
                self._mp_stop = None
                self._emit_connected(False)

            if self._stop_event.is_set():
                break

            logger.info(
                "Restarting BLE subprocess in 3s (fresh CoreBluetooth context)"
            )
            self._emit_status("BLE: restarting")
            await asyncio.sleep(3)

    async def _consume_events(
        self, event_queue: mp.Queue, process: mp.Process,
    ) -> None:
        """Read events from the BLE subprocess and dispatch them."""
        loop = asyncio.get_event_loop()

        while process.is_alive() and not self._stop_event.is_set():
            try:
                event = await loop.run_in_executor(
                    None, lambda: event_queue.get(timeout=1.0),
                )
            except queue.Empty:
                continue

            etype = event.get("type")

            if etype == "status":
                self._emit_status(f"BLE: {event['status']}")

            elif etype == "connected":
                self._emit_connected(event["connected"])

            elif etype == "devices":
                if self._on_devices is not None:
                    self._on_devices(event["devices"])

            elif etype in ("notification", "value"):
                data = bytearray(event["data"])
                blocking = self._parse_payload(data)
                if blocking is not None:
                    logger.info(
                        "BLE toggle from subprocess: blocking=%s", blocking,
                    )
                    await self._on_toggle(blocking)

            elif etype == "exit":
                logger.info(
                    "BLE subprocess requested exit: %s",
                    event.get("reason", "unknown"),
                )
                return

    # ------------------------------------------------------------------
    # Helpers (unchanged interface for LocalWebSocketServer / UI)
    # ------------------------------------------------------------------

    def _emit_status(self, status: str) -> None:
        if self._on_status is not None:
            self._on_status(status)

    def _emit_connected(self, connected: bool) -> None:
        if self._on_connected is not None:
            self._on_connected(connected)

    @staticmethod
    def _parse_payload(data: bytearray) -> Optional[bool]:
        if not data:
            logger.debug("Empty payload received")
            return None
        if len(data) == 1:
            result = bool(data[0])
            logger.debug(f"Single byte payload: {data[0]} -> {result}")
            return result
        try:
            payload = json.loads(data.decode("utf-8"))
            logger.debug(f"JSON payload: {payload}")
        except Exception as e:
            logger.warning(f"Failed to parse JSON payload: {e}")
            return None
        if isinstance(payload, dict) and "blocking" in payload:
            result = bool(payload.get("blocking"))
            logger.debug(f"Extracted blocking state from JSON: {result}")
            return result
        logger.debug("No blocking field in payload")
        return None


class LocalWebSocketServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 43111,
        token: Optional[str] = None,
        enable_ble: bool = True,
        ble_service_uuid: str = DEFAULT_BLE_SERVICE_UUID,
        ble_char_uuid: str = DEFAULT_BLE_CHAR_UUID,
        ble_device_name: Optional[str] = None,
        on_ble_status: Optional[Callable[[str], None]] = None,
        on_ble_devices: Optional[Callable[[List[str]], None]] = None,
        on_ble_connected: Optional[Callable[[bool], None]] = None,
        on_blocking_changed: Optional[Callable[[bool], None]] = None,
        log_queue: Optional[mp.Queue] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self._clients: Dict[WebSocketServerProtocol, ClientState] = {}
        self._server: Optional[websockets.server.Serve] = None
        self._store = BlocklistStore()
        self._ble_task: Optional[asyncio.Task] = None
        self._ble_client = None
        self._on_blocking_changed = on_blocking_changed
        self._ble_controlled = False  # True when the phone activated blocking
        if enable_ble:
            self._ble_client = BleToggleClient(
                self._handle_ble_toggle,
                service_uuid=ble_service_uuid,
                char_uuid=ble_char_uuid,
                device_name=ble_device_name,
                on_status=on_ble_status,
                on_devices=on_ble_devices,
                on_connected=on_ble_connected,
                log_queue=log_queue,
            )

    async def _handler(self, ws: WebSocketServerProtocol) -> None:
        self._clients[ws] = ClientState(authed=self.token is None)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "auth" and self.token is not None:
                    if msg.get("token") == self.token:
                        self._clients[ws].authed = True
                        await ws.send(json.dumps({"type": "auth_ok"}))
                    else:
                        await ws.send(json.dumps({"type": "auth_error"}))
                    continue
                if not self._clients[ws].authed:
                    await ws.send(json.dumps({"type": "auth_required"}))
                    continue
                await self._handle_message(ws, msg)
        finally:
            self._clients.pop(ws, None)

    async def _handle_message(self, ws: WebSocketServerProtocol, msg: dict) -> None:
        msg_type = msg.get("type")
        if msg_type == "request_state":
            await ws.send(json.dumps(self._state_payload()))
        elif msg_type == "set_blocking":
            blocking = bool(msg.get("blocking", False))
            state = self._store.set_blocking(blocking)
            await self._broadcast(self._state_payload(state))
        elif msg_type == "set_domains":
            domains = list(msg.get("domains", []))
            state = self._store.set_domains(domains)
            await self._broadcast(self._state_payload(state))
        else:
            await ws.send(json.dumps({"type": "error", "message": "unknown_message"}))

    async def _handle_ble_toggle(self, blocking: bool) -> None:
        logger.info(f"BLE reports blocking={blocking}, ble_controlled={self._ble_controlled}")

        if blocking:
            # Phone is activating blocking – always honour this.
            self._ble_controlled = True
        else:
            # Phone says "not blocking".  Only release if the phone was the
            # one that activated blocking; otherwise noop.
            if not self._ble_controlled:
                logger.info("BLE blocking=False ignored (phone did not set blocking)")
                return
            self._ble_controlled = False

        state = self._store.set_blocking(blocking)
        await self._broadcast(self._state_payload(state))
        if self._on_blocking_changed is not None:
            self._on_blocking_changed(blocking)

    def _state_payload(self, state=None) -> dict:
        if state is None:
            state = self._store.load()
        return {
            "type": "state",
            "blocking": state.blocking,
            "domains": state.domains,
            "version": state.version,
            "updated_at": state.updated_at,
        }

    async def _broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        data = json.dumps(payload)
        dead: Set[WebSocketServerProtocol] = set()
        for ws, client in self._clients.items():
            if not client.authed:
                continue
            try:
                await ws.send(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._clients.pop(ws, None)

    async def start(self) -> None:
        self._server = await websockets.serve(self._handler, self.host, self.port)
        if self._ble_client is not None:
            self._ble_task = asyncio.create_task(self._ble_client.run())

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._ble_client is not None:
            await self._ble_client.stop()
        if self._ble_task is not None:
            await self._ble_task

    def run_forever(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(self.start())
        loop.run_forever()
