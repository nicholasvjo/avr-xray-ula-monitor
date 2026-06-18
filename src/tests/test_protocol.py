from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from protocol import (  # noqa: E402
    EEPROM_SIZE,
    FLASH_SIZE,
    AdcState,
    HelloFrame,
    MemoryFrame,
    PortState,
    ProtocolError,
    SnapshotFrame,
    TimerState,
    UlaState,
    decode_eeprom_history,
    decode_line,
    encode_frame,
)


class ProtocolTests(unittest.TestCase):
    def test_hello_round_trip(self):
        frame = HelloFrame("AVR X-Ray", "1.0", 1, 10)
        self.assertEqual(decode_line(encode_frame(frame)), frame)

    def test_snapshot_round_trip(self):
        frame = SnapshotFrame(
            sequence=12,
            millis=3456,
            ula=UlaState(3, 7, 4, 10, 0, 3, 0),
            ports={
                "B": PortState(1, 2, 3),
                "C": PortState(4, 5, 6),
                "D": PortState(7, 8, 9),
            },
            sreg=0x82,
            timers=TimerState(1, 400, 2, 3, 4, 5, 6, 7, 8),
            adc=AdcState(512, 2502),
            sram=bytes(range(128)),
        )
        self.assertEqual(decode_line(encode_frame(frame)), frame)

    def test_memory_round_trip(self):
        frame = MemoryFrame(
            eeprom=bytes([0xFF] * EEPROM_SIZE),
            flash=bytes(range(FLASH_SIZE)),
        )
        self.assertEqual(decode_line(encode_frame(frame)), frame)

    def test_rejects_wrong_sram_size(self):
        payload = {
            "type": "snapshot",
            "protocol": 1,
            "seq": 1,
            "millis": 1,
            "ula": {
                "a": 0,
                "b": 0,
                "op": 0,
                "result": 0,
                "flags": 1,
                "stage": 0,
                "input": 0,
            },
            "ports": {
                name: {"ddr": 0, "port": 0, "pin": 0}
                for name in ("B", "C", "D")
            },
            "sreg": 0,
            "timers": {
                "tcnt0": 0,
                "tcnt1": 0,
                "tcnt2": 0,
                "tccr0a": 0,
                "tccr0b": 0,
                "tccr1a": 0,
                "tccr1b": 0,
                "tccr2a": 0,
                "tccr2b": 0,
            },
            "adc": {"a0": 0, "millivolts": 0},
            "sram": "00",
        }
        with self.assertRaises(ProtocolError):
            decode_line(json.dumps(payload))

    def test_decodes_eeprom_history_in_circular_order(self):
        data = bytearray([0xFF] * EEPROM_SIZE)
        data[0:4] = bytes((0xA5, 2, 2, 5))
        data[4:9] = bytes((1, 2, 4, 3, 0))
        data[9:14] = bytes((5, 3, 5, 2, 0))
        records = decode_eeprom_history(bytes(data))
        self.assertEqual([record["a"] for record in records], [1, 5])


if __name__ == "__main__":
    unittest.main()
