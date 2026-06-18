from __future__ import annotations

import queue
import time

from protocol import (
    FLAG_CARRY,
    FLAG_DIV_ZERO,
    FLAG_NEGATIVE,
    FLAG_OVERFLOW,
    FLAG_ZERO,
    HelloFrame,
    MemoryFrame,
    SnapshotFrame,
    decode_eeprom_history,
)
from serial_worker import SerialWorker, SourceEvent
from simulator import SimulatorWorker


def run_terminal_dashboard(
    port: str | None = None,
    baud: int = 115200,
    simulate: bool = False,
) -> None:
    events: queue.Queue[SourceEvent] = queue.Queue()
    source = (
        SimulatorWorker(events)
        if simulate
        else SerialWorker(events, port=port, baud=baud)
    )

    latest_snapshot: SnapshotFrame | None = None
    memory: MemoryFrame | None = None
    device = "Aguardando dispositivo"
    status = "Iniciando..."
    last_render = 0.0

    source.start()
    try:
        while True:
            try:
                event = events.get(timeout=0.1)
            except queue.Empty:
                event = None

            if event is not None:
                if event.kind == "status":
                    status = event.message
                elif event.kind in {"error", "protocol_error"}:
                    status = f"ERRO: {event.message}"
                elif event.kind == "frame":
                    if isinstance(event.data, HelloFrame):
                        device = (
                            f"{event.data.device} firmware {event.data.firmware}"
                        )
                    elif isinstance(event.data, SnapshotFrame):
                        latest_snapshot = event.data
                    elif isinstance(event.data, MemoryFrame):
                        memory = event.data

            now = time.monotonic()
            if latest_snapshot is not None and now - last_render >= 0.4:
                print("\033[2J\033[H", end="")
                print(_render_terminal(device, status, latest_snapshot, memory))
                last_render = now
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        source.stop()


def _render_terminal(
    device: str,
    status: str,
    frame: SnapshotFrame,
    memory: MemoryFrame | None,
) -> str:
    ula = frame.ula
    flag_values = (
        f"Z={int(bool(ula.flags & FLAG_ZERO))} "
        f"C={int(bool(ula.flags & FLAG_CARRY))} "
        f"N={int(bool(ula.flags & FLAG_NEGATIVE))} "
        f"V={int(bool(ula.flags & FLAG_OVERFLOW))} "
        f"D={int(bool(ula.flags & FLAG_DIV_ZERO))}"
    )

    lines = [
        "AVR X-Ray - ATmega328P Internal Monitor",
        "=" * 72,
        device,
        status,
        f"seq={frame.sequence} uptime={frame.millis / 1000:.1f}s",
        "",
        (
            f"ULA  A={ula.a:02d}/{ula.a:04b}  B={ula.b:02d}/{ula.b:04b}  "
            f"OP={ula.operation}:{ula.operation_name}  "
            f"R={ula.result:02d}/{ula.result:04b}"
        ),
        f"     stage={ula.stage_name} input={ula.input_value:04b}  {flag_values}",
        f"SREG 0x{frame.sreg:02X} / {frame.sreg:08b}",
        "",
    ]

    for name, state in frame.ports.items():
        lines.append(
            f"PORT{name} DDR={state.ddr:08b} PORT={state.port:08b} PIN={state.pin:08b}"
        )

    timers = frame.timers
    lines.extend(
        (
            "",
            (
                f"Timers TCNT0={timers.tcnt0:3d} "
                f"TCNT1={timers.tcnt1:5d} TCNT2={timers.tcnt2:3d}"
            ),
            (
                f"TCCR0 A=0x{timers.tccr0a:02X} B=0x{timers.tccr0b:02X} | "
                f"TCCR1 A=0x{timers.tccr1a:02X} B=0x{timers.tccr1b:02X} | "
                f"TCCR2 A=0x{timers.tccr2a:02X} B=0x{timers.tccr2b:02X}"
            ),
            f"ADC A0={frame.adc.a0:4d}/1023  {frame.adc.volts:.3f} V",
            "",
            "SRAM[0:32]",
            _short_hex(frame.sram[:32]),
        )
    )

    if memory is not None:
        history_count = len(decode_eeprom_history(memory.eeprom))
        lines.extend(
            (
                "",
                f"EEPROM={len(memory.eeprom)} bytes, history={history_count} records",
                f"FLASH={len(memory.flash)} bytes: {_short_hex(memory.flash[:16])}",
            )
        )
    else:
        lines.append("\nEEPROM/FLASH: aguardando GET_STATIC")

    lines.append("\nCtrl+C para sair.")
    return "\n".join(lines)


def _short_hex(data: bytes) -> str:
    return " ".join(f"{value:02X}" for value in data)
