from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 1
SRAM_SIZE = 128
EEPROM_SIZE = 192
FLASH_SIZE = 64

FLAG_ZERO = 1 << 0
FLAG_CARRY = 1 << 1
FLAG_NEGATIVE = 1 << 2
FLAG_OVERFLOW = 1 << 3
FLAG_DIV_ZERO = 1 << 4

OPERATION_NAMES = {
    0: "AND",
    1: "OR",
    2: "NOT(B)",
    3: "XOR",
    4: "ADD",
    5: "SUB",
    6: "MUL",
    7: "DIV",
}

STAGE_NAMES = {
    0: "INPUT_A",
    1: "INPUT_B",
    2: "INPUT_OPERATION",
    3: "RESULT",
}


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class HelloFrame:
    device: str
    firmware: str
    protocol: int
    sample_hz: int


@dataclass(frozen=True)
class UlaState:
    a: int
    b: int
    operation: int
    result: int
    flags: int
    stage: int
    input_value: int

    @property
    def operation_name(self) -> str:
        return OPERATION_NAMES.get(self.operation, f"OP {self.operation}")

    @property
    def stage_name(self) -> str:
        return STAGE_NAMES.get(self.stage, f"STAGE {self.stage}")

    def flag(self, mask: int) -> bool:
        return bool(self.flags & mask)


@dataclass(frozen=True)
class PortState:
    ddr: int
    port: int
    pin: int


@dataclass(frozen=True)
class TimerState:
    tcnt0: int
    tcnt1: int
    tcnt2: int
    tccr0a: int
    tccr0b: int
    tccr1a: int
    tccr1b: int
    tccr2a: int
    tccr2b: int


@dataclass(frozen=True)
class AdcState:
    a0: int
    millivolts: int

    @property
    def volts(self) -> float:
        return self.millivolts / 1000.0


@dataclass(frozen=True)
class SnapshotFrame:
    sequence: int
    millis: int
    ula: UlaState
    ports: dict[str, PortState]
    sreg: int
    timers: TimerState
    adc: AdcState
    sram: bytes


@dataclass(frozen=True)
class MemoryFrame:
    eeprom: bytes
    flash: bytes


ProtocolFrame = HelloFrame | SnapshotFrame | MemoryFrame


def decode_line(line: str | bytes) -> ProtocolFrame:
    if isinstance(line, bytes):
        try:
            line = line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ProtocolError("A mensagem nao e ASCII.") from exc

    try:
        payload = json.loads(line.strip())
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"JSON invalido: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ProtocolError("A raiz da mensagem deve ser um objeto JSON.")

    protocol = _required_int(payload, "protocol")
    if protocol != PROTOCOL_VERSION:
        raise ProtocolError(
            f"Versao de protocolo incompatível: {protocol}, esperada {PROTOCOL_VERSION}."
        )

    frame_type = payload.get("type")
    if frame_type == "hello":
        return HelloFrame(
            device=_required_str(payload, "device"),
            firmware=_required_str(payload, "firmware"),
            protocol=protocol,
            sample_hz=_bounded_int(payload, "sample_hz", 1, 100),
        )
    if frame_type == "snapshot":
        return _decode_snapshot(payload)
    if frame_type == "memory":
        return MemoryFrame(
            eeprom=_decode_hex(payload, "eeprom", EEPROM_SIZE),
            flash=_decode_hex(payload, "flash", FLASH_SIZE),
        )

    raise ProtocolError(f"Tipo de mensagem desconhecido: {frame_type!r}.")


def encode_get_static() -> bytes:
    return b"GET_STATIC\n"


def encode_frame(frame: ProtocolFrame) -> str:
    if isinstance(frame, HelloFrame):
        payload: dict[str, Any] = {
            "type": "hello",
            "protocol": frame.protocol,
            "device": frame.device,
            "firmware": frame.firmware,
            "sample_hz": frame.sample_hz,
        }
    elif isinstance(frame, SnapshotFrame):
        payload = {
            "type": "snapshot",
            "protocol": PROTOCOL_VERSION,
            "seq": frame.sequence,
            "millis": frame.millis,
            "ula": {
                "a": frame.ula.a,
                "b": frame.ula.b,
                "op": frame.ula.operation,
                "result": frame.ula.result,
                "flags": frame.ula.flags,
                "stage": frame.ula.stage,
                "input": frame.ula.input_value,
            },
            "ports": {
                name: {
                    "ddr": state.ddr,
                    "port": state.port,
                    "pin": state.pin,
                }
                for name, state in frame.ports.items()
            },
            "sreg": frame.sreg,
            "timers": {
                "tcnt0": frame.timers.tcnt0,
                "tcnt1": frame.timers.tcnt1,
                "tcnt2": frame.timers.tcnt2,
                "tccr0a": frame.timers.tccr0a,
                "tccr0b": frame.timers.tccr0b,
                "tccr1a": frame.timers.tccr1a,
                "tccr1b": frame.timers.tccr1b,
                "tccr2a": frame.timers.tccr2a,
                "tccr2b": frame.timers.tccr2b,
            },
            "adc": {
                "a0": frame.adc.a0,
                "millivolts": frame.adc.millivolts,
            },
            "sram": bytes_to_hex(frame.sram),
        }
    elif isinstance(frame, MemoryFrame):
        payload = {
            "type": "memory",
            "protocol": PROTOCOL_VERSION,
            "eeprom": bytes_to_hex(frame.eeprom),
            "flash": bytes_to_hex(frame.flash),
        }
    else:
        raise TypeError(f"Tipo de frame nao suportado: {type(frame)!r}")
    return json.dumps(payload, separators=(",", ":")) + "\n"


def bytes_to_hex(data: bytes | bytearray) -> str:
    return bytes(data).hex().upper()


def decode_eeprom_history(data: bytes) -> list[dict[str, int | str]]:
    if len(data) < 4 or data[0] != 0xA5:
        return []

    write_index = data[1] % 32
    count = min(data[2], 32)
    record_size = data[3]
    if record_size != 5:
        return []

    records: list[dict[str, int | str]] = []
    start = (write_index - count) % 32
    for offset in range(count):
        record_index = (start + offset) % 32
        base = 4 + record_index * record_size
        if base + record_size > len(data):
            break
        a, b, operation, result, flags = data[base : base + record_size]
        records.append(
            {
                "index": record_index,
                "a": a,
                "b": b,
                "operation": operation,
                "operation_name": OPERATION_NAMES.get(operation, f"OP {operation}"),
                "result": result,
                "flags": flags,
            }
        )
    return records


def sram_meaning(index: int) -> str:
    meanings = {
        0: "ULA operand A",
        1: "ULA operand B",
        2: "ULA operation code",
        3: "ULA result",
        4: "ULA flags: D V N C Z",
        5: "CPU status register SREG",
        6: "PORTB",
        7: "PORTC",
        8: "PORTD",
        9: "PINB",
        10: "PINC",
        11: "PIND",
        12: "TCNT0",
        13: "TCNT2",
        14: "ADC A0 low byte",
        15: "ADC A0 high byte",
    }
    if index in meanings:
        return meanings[index]
    if 16 <= index < 128:
        slot = (index - 16) // 7
        field = (index - 16) % 7
        field_names = ("A", "B", "operation", "result", "flags", "SREG", "sequence")
        return f"ULA circular history slot {slot}, {field_names[field]}"
    return "Unmapped SRAM byte"


def _decode_snapshot(payload: dict[str, Any]) -> SnapshotFrame:
    ula_data = _required_dict(payload, "ula")
    ports_data = _required_dict(payload, "ports")
    timers_data = _required_dict(payload, "timers")
    adc_data = _required_dict(payload, "adc")

    ports: dict[str, PortState] = {}
    for name in ("B", "C", "D"):
        item = _required_dict(ports_data, name)
        ports[name] = PortState(
            ddr=_bounded_int(item, "ddr", 0, 255),
            port=_bounded_int(item, "port", 0, 255),
            pin=_bounded_int(item, "pin", 0, 255),
        )

    return SnapshotFrame(
        sequence=_required_int(payload, "seq"),
        millis=_required_int(payload, "millis"),
        ula=UlaState(
            a=_bounded_int(ula_data, "a", 0, 15),
            b=_bounded_int(ula_data, "b", 0, 15),
            operation=_bounded_int(ula_data, "op", 0, 7),
            result=_bounded_int(ula_data, "result", 0, 15),
            flags=_bounded_int(ula_data, "flags", 0, 31),
            stage=_bounded_int(ula_data, "stage", 0, 3),
            input_value=_bounded_int(ula_data, "input", 0, 15),
        ),
        ports=ports,
        sreg=_bounded_int(payload, "sreg", 0, 255),
        timers=TimerState(
            tcnt0=_bounded_int(timers_data, "tcnt0", 0, 255),
            tcnt1=_bounded_int(timers_data, "tcnt1", 0, 65535),
            tcnt2=_bounded_int(timers_data, "tcnt2", 0, 255),
            tccr0a=_bounded_int(timers_data, "tccr0a", 0, 255),
            tccr0b=_bounded_int(timers_data, "tccr0b", 0, 255),
            tccr1a=_bounded_int(timers_data, "tccr1a", 0, 255),
            tccr1b=_bounded_int(timers_data, "tccr1b", 0, 255),
            tccr2a=_bounded_int(timers_data, "tccr2a", 0, 255),
            tccr2b=_bounded_int(timers_data, "tccr2b", 0, 255),
        ),
        adc=AdcState(
            a0=_bounded_int(adc_data, "a0", 0, 1023),
            millivolts=_bounded_int(adc_data, "millivolts", 0, 5500),
        ),
        sram=_decode_hex(payload, "sram", SRAM_SIZE),
    )


def _required_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ProtocolError(f"Campo {key!r} deve ser um objeto.")
    return value


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"Campo {key!r} deve ser inteiro.")
    return value


def _bounded_int(payload: dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    value = _required_int(payload, key)
    if not minimum <= value <= maximum:
        raise ProtocolError(
            f"Campo {key!r} fora da faixa {minimum}..{maximum}: {value}."
        )
    return value


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"Campo {key!r} deve ser texto nao vazio.")
    return value


def _decode_hex(payload: dict[str, Any], key: str, expected_size: int) -> bytes:
    value = _required_str(payload, key)
    if len(value) != expected_size * 2:
        raise ProtocolError(
            f"Campo {key!r} deve conter {expected_size} bytes em hexadecimal."
        )
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise ProtocolError(f"Campo {key!r} possui hexadecimal invalido.") from exc
