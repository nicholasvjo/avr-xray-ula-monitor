from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any

import serial
from serial.tools import list_ports

from protocol import ProtocolError, ProtocolFrame, decode_line, encode_get_static


@dataclass(frozen=True)
class SourceEvent:
    kind: str
    data: Any = None
    message: str = ""


def list_serial_ports() -> list[tuple[str, str]]:
    ports = []
    for port in list_ports.comports():
        description = port.description or "Serial device"
        ports.append((port.device, description))
    return sorted(ports, key=lambda item: item[0].lower())


def choose_serial_port(port: str | None, available: list[tuple[str, str]]) -> str:
    if port:
        return port
    if not available:
        raise RuntimeError("Nenhuma porta serial foi encontrada.")
    if len(available) == 1:
        return available[0][0]

    keywords = ("arduino", "usb serial", "ch340", "wch", "ttyacm", "ttyusb")
    matches = [
        device
        for device, description in available
        if any(
            keyword in f"{device} {description}".lower()
            for keyword in keywords
        )
    ]
    if len(matches) == 1:
        return matches[0]

    devices = ", ".join(device for device, _ in available)
    raise RuntimeError(
        f"Varias portas seriais encontradas ({devices}). Selecione uma porta."
    )


class SerialWorker:
    def __init__(
        self,
        events: queue.Queue[SourceEvent],
        port: str | None = None,
        baud: int = 115200,
    ):
        self.events = events
        self.requested_port = port
        self.baud = baud
        self.active_port: str | None = None
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._write_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        serial_connection = self._serial
        if serial_connection is not None:
            try:
                serial_connection.close()
            except serial.SerialException:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        self._serial = None

    def request_static(self) -> None:
        self.send(encode_get_static())

    def send(self, payload: bytes) -> None:
        serial_connection = self._serial
        if serial_connection is None or not serial_connection.is_open:
            return
        with self._write_lock:
            try:
                serial_connection.write(payload)
                serial_connection.flush()
            except serial.SerialException as exc:
                self.events.put(
                    SourceEvent("error", message=f"Falha ao enviar comando: {exc}")
                )

    def _run(self) -> None:
        try:
            self.active_port = choose_serial_port(
                self.requested_port,
                list_serial_ports(),
            )
            self.events.put(
                SourceEvent(
                    "status",
                    data="connecting",
                    message=f"Conectando a {self.active_port}...",
                )
            )
            self._serial = serial.Serial(
                self.active_port,
                self.baud,
                timeout=0.25,
                write_timeout=1.0,
            )
            self.events.put(
                SourceEvent(
                    "status",
                    data="connected",
                    message=f"Conectado a {self.active_port} @ {self.baud}.",
                )
            )
            self.request_static()

            while not self._stop_event.is_set():
                raw_line = self._serial.readline()
                if not raw_line:
                    continue
                try:
                    frame = decode_line(raw_line)
                except ProtocolError as exc:
                    self.events.put(
                        SourceEvent("protocol_error", message=str(exc))
                    )
                    continue
                self._publish_frame(frame)
        except (serial.SerialException, RuntimeError) as exc:
            if not self._stop_event.is_set():
                self.events.put(SourceEvent("error", message=str(exc)))
        finally:
            serial_connection = self._serial
            if serial_connection is not None:
                try:
                    serial_connection.close()
                except serial.SerialException:
                    pass
            self._serial = None
            self.events.put(
                SourceEvent("status", data="disconnected", message="Desconectado.")
            )

    def _publish_frame(self, frame: ProtocolFrame) -> None:
        self.events.put(SourceEvent("frame", data=frame))
