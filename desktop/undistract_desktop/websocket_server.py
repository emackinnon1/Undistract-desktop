from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

from .blocklist_store import BlocklistStore
from bleak import BleakClient, BleakScanner

logger = logging.getLogger(__name__)


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
        on_devices: Optional[Callable[[List[str]], None]] = None,
        on_connected: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self._on_toggle = on_toggle
        self._service_uuid = service_uuid.lower()
        self._char_uuid = char_uuid
        self._device_name = device_name
        self._on_status = on_status
        self._on_devices = on_devices
        self._on_connected = on_connected
        self._stop_event = asyncio.Event()

    async def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        logger.info("BLE client starting")
        while not self._stop_event.is_set():
            logger.info("Starting BLE device scan")
            self._emit_status("BLE: scanning")
            device = await self._discover_device()
            if device is None:
                logger.warning("No matching BLE device found")
                self._emit_status("BLE: not found")
                await asyncio.sleep(1)
                continue
            try:
                logger.info(f"Attempting to connect to BLE device: {device.name or device.address}")
                self._emit_status(f"BLE: connecting to {device.name or device.address}")
                async with BleakClient(device) as client:
                    logger.info(f"Successfully connected to {device.name or device.address}")
                    logger.info(f"Subscribing to characteristic {self._char_uuid}")
                    self._emit_status("BLE: connected")
                    self._emit_connected(True)
                    await client.start_notify(self._char_uuid, self._handle_notification)
                    logger.info("Subscribed to notifications")
                    
                    # Read the initial blocking state
                    try:
                        initial_value = await client.read_gatt_char(self._char_uuid)
                        logger.info(f"Read initial characteristic value: {initial_value.hex()}")
                        initial_blocking = self._parse_payload(initial_value)
                        if initial_blocking is not None:
                            logger.info(f"Initial blocking state: {initial_blocking}")
                            await self._on_toggle(initial_blocking)
                    except Exception as e:
                        logger.warning(f"Failed to read initial characteristic value: {e}")
                    
                    # Periodic health check to detect stale connections (e.g., after sleep)
                    health_check_interval = 30  # seconds
                    last_health_check = asyncio.get_event_loop().time()
                    
                    while client.is_connected and not self._stop_event.is_set():
                        await asyncio.sleep(1)
                        
                        # Perform periodic health check by reading the characteristic
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_health_check >= health_check_interval:
                            try:
                                logger.debug("Performing BLE connection health check")
                                # Try to read with a timeout to detect stale connections
                                value = await asyncio.wait_for(
                                    client.read_gatt_char(self._char_uuid),
                                    timeout=5.0
                                )
                                logger.debug(f"Health check successful, value: {value.hex()}")
                                last_health_check = current_time
                            except asyncio.TimeoutError:
                                logger.warning("Health check timed out, connection may be stale")
                                raise  # This will cause reconnection
                            except Exception as e:
                                logger.warning(f"Health check failed: {e}")
                                raise  # This will cause reconnection
            except Exception as e:
                logger.error(f"BLE connection error: {e}", exc_info=True)
                self._emit_status("BLE: disconnected")
                self._emit_connected(False)
                # Shorter retry delay for faster recovery after sleep/wake
                await asyncio.sleep(1)

    async def _discover_device(self):
        logger.info("Discovering BLE devices...")
        discovery = await BleakScanner.discover(timeout=4.0, return_adv=True)
        logger.info(f"Found {len(discovery)} BLE devices")

        for i, (address, (device, adv)) in enumerate(discovery.items()):
            name = adv.local_name or device.name or "Unknown"
            service_uuids = [u.lower() for u in adv.service_uuids]
            logger.info(
                f"  Device {i+1}/{len(discovery)}: {name} ({address}), "
                f"RSSI: {adv.rssi}, Service UUIDs: {service_uuids}"
            )

        self._emit_devices(list(discovery.values()))

        for address, (device, adv) in discovery.items():
            name = adv.local_name or device.name
            if self._device_name and name != self._device_name:
                logger.debug(f"Skipping device {name or address} (name mismatch)")
                continue
            service_uuids = [u.lower() for u in adv.service_uuids]
            if self._service_uuid in service_uuids:
                logger.info(
                    f"Found matching device: {name or address} "
                    f"with service UUID {self._service_uuid}"
                )
                return device

        logger.warning(f"No device found advertising service UUID {self._service_uuid}")
        return None

    def _emit_devices(self, device_adv_pairs) -> None:
        if self._on_devices is None:
            logger.debug("No on_devices callback registered")
            return
        names = []
        for device, adv in device_adv_pairs:
            label = adv.local_name or device.name or device.address
            if adv.rssi is not None:
                label = f"{label} (RSSI {adv.rssi})"
            if adv.service_uuids:
                label = f"{label}  services: {adv.service_uuids}"
            names.append(label)
        logger.info(f"Emitting {len(names)} devices to callback")
        self._on_devices(names)

    def _handle_notification(self, _sender, data: bytearray) -> None:
        logger.info(f"Received BLE notification: {data.hex()}")
        blocking = self._parse_payload(data)
        if blocking is None:
            logger.warning(f"Could not parse notification payload: {data}")
            return
        logger.info(f"Parsed blocking state: {blocking}")
        asyncio.create_task(self._on_toggle(blocking))

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
        if enable_ble:
            self._ble_client = BleToggleClient(
                self._handle_ble_toggle,
                service_uuid=ble_service_uuid,
                char_uuid=ble_char_uuid,
                device_name=ble_device_name,
                on_status=on_ble_status,
                on_devices=on_ble_devices,
                on_connected=on_ble_connected,
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
        logger.info(f"BLE toggled blocking state to: {blocking}")
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
