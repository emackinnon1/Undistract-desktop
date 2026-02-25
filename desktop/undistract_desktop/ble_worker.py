"""BLE worker that runs in a child subprocess.

Each subprocess gets a completely fresh CoreBluetooth context, which is
the only reliable way to recover from macOS sleep/wake BLE connection
issues.  Communication with the parent process is via a
``multiprocessing.Queue`` of small JSON-serialisable dicts.

Event types emitted → parent:
    {"type": "status",       "status": "<text>"}
    {"type": "connected",    "connected": true|false}
    {"type": "devices",      "devices": ["label", ...]}
    {"type": "notification", "data": [int, ...]}
    {"type": "value",        "data": [int, ...]}   # only on connect or when value changes
    {"type": "exit",         "reason": "<text>"}
"""
from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import time
from multiprocessing import Queue
from multiprocessing.synchronize import Event as MpEvent
from typing import Optional


# ---------------------------------------------------------------------------
# Constants (subprocess-local)
# ---------------------------------------------------------------------------
SLEEP_DETECTION_SECS = 5
HEALTH_CHECK_INTERVAL_SECS = 10
CONNECT_TIMEOUT_SECS = 15.0
GATT_READ_TIMEOUT_SECS = 5.0
SCAN_TIMEOUT_SECS = 5.0
# After this many consecutive "device found but connect timed out" failures
# the subprocess exits so the parent can spawn a fresh one.
MAX_CONNECT_TIMEOUTS = 3


def _emit(q: Queue, event: dict) -> None:
    """Non-blocking put; silently drops if the queue is full."""
    try:
        q.put_nowait(event)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public entry point – called by multiprocessing.Process(target=...)
# ---------------------------------------------------------------------------
def run_ble_worker(
    event_queue: Queue,
    stop_event: MpEvent,
    log_queue: Optional[Queue],
    service_uuid: str,
    char_uuid: str,
    device_name: Optional[str],
) -> None:
    """Scan → connect → subscribe → health-check loop.

    Exits (allowing the parent to spawn a fresh subprocess) when:
    * ``MAX_CONNECT_TIMEOUTS`` consecutive connect timeouts are hit
      (CoreBluetooth is stuck).
    * A system sleep/wake is detected via wall-clock jump.
    * ``stop_event`` is set by the parent.
    """
    # ---- logging (subprocess) ----
    # All file I/O (including rotation) is centralised in the parent
    # process via QueueHandler → QueueListener.  The subprocess only
    # writes to stderr directly.
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_queue is not None:
        handlers.append(logging.handlers.QueueHandler(log_queue))
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )
    logger = logging.getLogger("ble_worker")
    logger.info("BLE worker subprocess started (pid=%d)", os.getpid())

    # Import bleak *inside* the subprocess so it initialises a completely
    # fresh CoreBluetooth stack.
    from bleak import BleakClient, BleakScanner  # noqa: E402

    def emit(event: dict) -> None:
        _emit(event_queue, event)

    # ------------------------------------------------------------------
    async def _run() -> None:
        connect_timeouts = 0

        while not stop_event.is_set():
            # ---- Scan ----
            emit({"type": "status", "status": "scanning"})
            logger.info("Scanning for BLE devices...")

            pre_scan = time.time()
            try:
                discovery = await BleakScanner.discover(
                    timeout=SCAN_TIMEOUT_SECS, return_adv=True,
                )
            except Exception as exc:
                logger.error("Scan failed: %s", exc)
                emit({"type": "status", "status": f"scan error: {exc}"})
                await asyncio.sleep(2)
                continue

            scan_wall = time.time() - pre_scan
            if scan_wall > SCAN_TIMEOUT_SECS + SLEEP_DETECTION_SECS:
                logger.info(
                    "Sleep detected during scan (wall %.1fs for %.0fs scan)",
                    scan_wall, SCAN_TIMEOUT_SECS,
                )
                emit({"type": "exit", "reason": "sleep_detected_during_scan"})
                return

            logger.info("Found %d BLE devices", len(discovery))

            # Build device labels for the parent UI
            labels: list[str] = []
            for _addr, (dev, adv) in discovery.items():
                name = adv.local_name or dev.name or "Unknown"
                lbl = name
                if adv.rssi is not None:
                    lbl += f" (RSSI {adv.rssi})"
                if adv.service_uuids:
                    lbl += f"  services: {adv.service_uuids}"
                labels.append(lbl)
            emit({"type": "devices", "devices": labels})

            # Find the target device
            target = None
            for _addr, (dev, adv) in discovery.items():
                name = adv.local_name or dev.name
                if device_name and name != device_name:
                    continue
                svc_uuids = [u.lower() for u in (adv.service_uuids or [])]
                if service_uuid.lower() in svc_uuids:
                    logger.info("Found target: %s (%s)", name, dev.address)
                    target = dev
                    break

            if target is None:
                logger.warning("Target device not found")
                emit({"type": "status", "status": "not found"})
                await asyncio.sleep(2)
                continue

            # ---- Connect ----
            target_label = target.name or target.address
            emit({"type": "status", "status": f"connecting to {target_label}"})
            logger.info("Connecting to %s", target_label)

            client = BleakClient(target)
            pre_connect = time.time()

            try:
                await asyncio.wait_for(
                    client.connect(), timeout=CONNECT_TIMEOUT_SECS,
                )
            except asyncio.TimeoutError:
                connect_wall = time.time() - pre_connect
                if connect_wall > CONNECT_TIMEOUT_SECS + SLEEP_DETECTION_SECS:
                    logger.info(
                        "Sleep detected during connect (wall %.1fs)", connect_wall,
                    )
                    emit({"type": "exit", "reason": "sleep_detected_during_connect"})
                    return

                connect_timeouts += 1
                logger.error(
                    "Connect timed out (%d/%d)",
                    connect_timeouts, MAX_CONNECT_TIMEOUTS,
                )
                emit({
                    "type": "status",
                    "status": (
                        f"connect timeout ({connect_timeouts}/{MAX_CONNECT_TIMEOUTS})"
                    ),
                })
                if connect_timeouts >= MAX_CONNECT_TIMEOUTS:
                    logger.warning(
                        "Persistent connect timeouts – CoreBluetooth likely stuck. "
                        "Exiting subprocess for fresh restart."
                    )
                    emit({"type": "exit", "reason": "connect_stuck"})
                    return

                await asyncio.sleep(2)
                continue

            except Exception as exc:
                connect_timeouts += 1
                logger.error("Connect error (%d): %s", connect_timeouts, exc)
                if connect_timeouts >= MAX_CONNECT_TIMEOUTS:
                    emit({"type": "exit", "reason": "connect_stuck"})
                    return
                await asyncio.sleep(2)
                continue

            # ---- Connected ----
            connect_timeouts = 0
            logger.info("Connected to %s", target_label)
            emit({"type": "connected", "connected": True})
            emit({"type": "status", "status": "connected"})

            try:
                # Subscribe to notifications
                def _on_notify(_sender: int, data: bytearray) -> None:
                    emit({"type": "notification", "data": list(data)})

                await client.start_notify(char_uuid, _on_notify)
                logger.info("Subscribed to BLE notifications")

                # Read initial characteristic value
                last_value: Optional[list] = None
                try:
                    initial = await asyncio.wait_for(
                        client.read_gatt_char(char_uuid),
                        timeout=GATT_READ_TIMEOUT_SECS,
                    )
                    logger.info("Initial value: %s", initial.hex())
                    last_value = list(initial)
                    emit({"type": "value", "data": last_value})
                except Exception as exc:
                    logger.warning("Initial read failed: %s", exc)

                # ---- Stay-connected loop ----
                last_health = time.time()

                while not stop_event.is_set():
                    wall_before = time.time()
                    await asyncio.sleep(1)
                    wall_after = time.time()
                    elapsed = wall_after - wall_before

                    # Sleep detection
                    if elapsed > SLEEP_DETECTION_SECS:
                        logger.info(
                            "Sleep detected while connected "
                            "(asyncio.sleep(1) took %.1fs). Exiting subprocess.",
                            elapsed,
                        )
                        emit({"type": "exit", "reason": "sleep_detected_while_connected"})
                        return

                    if not client.is_connected:
                        logger.info("BLE disconnected")
                        break

                    # Periodic health-check + state sync
                    if wall_after - last_health >= HEALTH_CHECK_INTERVAL_SECS:
                        try:
                            value = await asyncio.wait_for(
                                client.read_gatt_char(char_uuid),
                                timeout=GATT_READ_TIMEOUT_SECS,
                            )
                            logger.debug("Health check OK: %s", value.hex())
                            current = list(value)
                            if current != last_value:
                                logger.info(
                                    "BLE value changed: %s -> %s",
                                    last_value, current,
                                )
                                last_value = current
                                emit({"type": "value", "data": current})
                            last_health = wall_after
                        except Exception as exc:
                            logger.warning("Health check failed: %s", exc)
                            break

            finally:
                try:
                    if client.is_connected:
                        await client.disconnect()
                except Exception:
                    pass
                emit({"type": "connected", "connected": False})
                emit({"type": "status", "status": "disconnected"})

            # Brief pause before next scan cycle
            await asyncio.sleep(1)

    # ------------------------------------------------------------------
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logger.error("Worker crashed: %s", exc, exc_info=True)
        emit({"type": "exit", "reason": f"crash: {exc}"})
    finally:
        logger.info("BLE worker subprocess exiting")
