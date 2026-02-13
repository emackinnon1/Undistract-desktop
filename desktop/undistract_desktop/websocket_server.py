from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

from .blocklist_store import BlocklistStore
from bleak import BleakClient, BleakScanner


DEFAULT_BLE_SERVICE_UUID = "a4f7e000-0000-1000-8000-00805f9b34fb"
DEFAULT_BLE_CHAR_UUID = "a4f7e001-0000-1000-8000-00805f9b34fb"


@dataclass
class ClientState:
    authed: bool = False


class BleToggleClient:
    def __init__(
        self,
        on_toggle,
        service_uuid: str = DEFAULT_BLE_SERVICE_UUID,
        char_uuid: str = DEFAULT_BLE_CHAR_UUID,
        device_name: Optional[str] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_toggle = on_toggle
        self._service_uuid = service_uuid.lower()
        self._char_uuid = char_uuid
        self._device_name = device_name
        self._on_status = on_status
        self._stop_event = asyncio.Event()

    async def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        while not self._stop_event.is_set():
            self._emit_status("BLE: scanning")
            device = await self._discover_device()
            if device is None:
                self._emit_status("BLE: not found")
                await asyncio.sleep(2)
                continue
            try:
                self._emit_status(f"BLE: connecting to {device.name or device.address}")
                async with BleakClient(device) as client:
                    self._emit_status("BLE: connected")
                    await client.start_notify(self._char_uuid, self._handle_notification)
                    while client.is_connected and not self._stop_event.is_set():
                        await asyncio.sleep(1)
            except Exception:
                self._emit_status("BLE: disconnected")
                await asyncio.sleep(2)

    async def _discover_device(self):
        devices = await BleakScanner.discover(timeout=4.0)
        for d in devices:
            if self._device_name and d.name != self._device_name:
                continue
            service_uuids = [s.lower() for s in (d.metadata.get("uuids") or [])]
            if self._service_uuid in service_uuids:
                return d
        return None

    def _handle_notification(self, _sender, data: bytearray) -> None:
        blocking = self._parse_payload(data)
        if blocking is None:
            return
        asyncio.create_task(self._on_toggle(blocking))

    def _emit_status(self, status: str) -> None:
        if self._on_status is not None:
            self._on_status(status)

    @staticmethod
    def _parse_payload(data: bytearray) -> Optional[bool]:
        if not data:
            return None
        if len(data) == 1:
            return bool(data[0])
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            return None
        if isinstance(payload, dict) and "blocking" in payload:
            return bool(payload.get("blocking"))
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
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self._clients: Dict[WebSocketServerProtocol, ClientState] = {}
        self._server: Optional[websockets.server.Serve] = None
        self._store = BlocklistStore()
        self._ble_task: Optional[asyncio.Task] = None
        self._ble_client = None
        if enable_ble:
            self._ble_client = BleToggleClient(
                self._handle_ble_toggle,
                service_uuid=ble_service_uuid,
                char_uuid=ble_char_uuid,
                device_name=ble_device_name,
                on_status=on_ble_status,
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
        state = self._store.set_blocking(blocking)
        await self._broadcast(self._state_payload(state))

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
