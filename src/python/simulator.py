from __future__ import annotations

import math
import queue
import random
import threading
import time

from protocol import (
    AdcState,
    EEPROM_SIZE,
    FLASH_SIZE,
    HelloFrame,
    MemoryFrame,
    PortState,
    SnapshotFrame,
    TimerState,
    UlaState,
    decode_line,
    encode_frame,
)
from serial_worker import SourceEvent
from ula_reference import execute_ula


class SimulatorWorker:
    def __init__(self, events: queue.Queue[SourceEvent], sample_hz: int = 10):
        self.events = events
        self.sample_hz = sample_hz
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._static_requested = threading.Event()
        self._rng = random.Random(328)
        self._eeprom = self._build_eeprom()
        self._flash = bytes((index * 37 + 0x5A) & 0xFF for index in range(FLASH_SIZE))

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._static_requested.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

    def request_static(self) -> None:
        self._static_requested.set()

    def _run(self) -> None:
        self.events.put(
            SourceEvent("status", data="connected", message="Simulador conectado.")
        )
        self._emit_frame(
            HelloFrame(
                device="Simulador AVR X-Ray",
                firmware="1.0-sim",
                protocol=1,
                sample_hz=self.sample_hz,
            )
        )

        sequence = 0
        start = time.monotonic()
        interval = 1.0 / self.sample_hz
        next_tick = time.monotonic()

        try:
            while not self._stop_event.is_set():
                if self._static_requested.is_set():
                    self._static_requested.clear()
                    self._emit_frame(
                        MemoryFrame(
                            eeprom=bytes(self._eeprom),
                            flash=self._flash,
                        )
                    )

                now = time.monotonic()
                if now < next_tick:
                    self._stop_event.wait(min(next_tick - now, 0.05))
                    continue

                sequence += 1
                elapsed = now - start
                self._emit_frame(self._snapshot(sequence, elapsed))
                next_tick += interval
        finally:
            self.events.put(
                SourceEvent("status", data="disconnected", message="Simulador parado.")
            )

    def _snapshot(self, sequence: int, elapsed: float) -> SnapshotFrame:
        operation = (sequence // 25) % 8
        a = (sequence // 7) & 0x0F
        b = (sequence // 11 + 3) & 0x0F
        ula_result = execute_ula(a, b, operation)
        input_value = (sequence // 3) & 0x0F
        stage = (sequence // 18) % 4
        millis = int(elapsed * 1000)
        adc = int((math.sin(elapsed * 0.9) * 0.5 + 0.5) * 1023)

        ports = {
            "B": PortState(ddr=0x1F, port=ula_result.result, pin=(sequence * 3) & 0xFF),
            "C": PortState(ddr=0x00, port=0x00, pin=(adc >> 2) & 0xFF),
            "D": PortState(ddr=0x7C, port=0x80, pin=(~sequence) & 0xFF),
        }
        sreg = (
            (0x80 if sequence % 2 else 0)
            | (ula_result.flags & 0x0F)
            | (0x10 if ula_result.result & 0x08 else 0)
        )
        timers = TimerState(
            tcnt0=(millis // 1) & 0xFF,
            tcnt1=(millis * 16) & 0xFFFF,
            tcnt2=(millis // 4) & 0xFF,
            tccr0a=0x03,
            tccr0b=0x03,
            tccr1a=0x00,
            tccr1b=0x00,
            tccr2a=0x01,
            tccr2b=0x04,
        )

        sram = bytearray(128)
        sram[0:16] = bytes(
            (
                a,
                b,
                operation,
                ula_result.result,
                ula_result.flags,
                sreg,
                ports["B"].port,
                ports["C"].port,
                ports["D"].port,
                ports["B"].pin,
                ports["C"].pin,
                ports["D"].pin,
                timers.tcnt0,
                timers.tcnt2,
                adc & 0xFF,
                (adc >> 8) & 0xFF,
            )
        )
        for index in range(16, 128):
            phase = index * 0.13 + elapsed * (0.4 + (index % 5) * 0.07)
            sram[index] = int((math.sin(phase) * 0.5 + 0.5) * 255)
        for _ in range(3):
            cell = self._rng.randrange(16, 128)
            sram[cell] = self._rng.randrange(256)

        return SnapshotFrame(
            sequence=sequence,
            millis=millis,
            ula=UlaState(
                a=a,
                b=b,
                operation=operation,
                result=ula_result.result,
                flags=ula_result.flags,
                stage=stage,
                input_value=input_value,
            ),
            ports=ports,
            sreg=sreg,
            timers=timers,
            adc=AdcState(
                a0=adc,
                millivolts=round(adc * 5000 / 1023),
            ),
            sram=bytes(sram),
        )

    def _build_eeprom(self) -> bytearray:
        data = bytearray([0xFF] * EEPROM_SIZE)
        data[0:4] = bytes((0xA5, 8, 8, 5))
        for index in range(8):
            a = index & 0x0F
            b = (index * 2 + 1) & 0x0F
            operation = index
            result = execute_ula(a, b, operation)
            base = 4 + index * 5
            data[base : base + 5] = bytes(
                (a, b, operation, result.result, result.flags)
            )
        return data

    def _emit_frame(self, frame: HelloFrame | SnapshotFrame | MemoryFrame) -> None:
        parsed = decode_line(encode_frame(frame))
        self.events.put(SourceEvent("frame", data=parsed))
