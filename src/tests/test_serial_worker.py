from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from serial_worker import choose_serial_port  # noqa: E402


class SerialSelectionTests(unittest.TestCase):
    def test_explicit_port_wins(self):
        self.assertEqual(
            choose_serial_port("COM9", [("COM3", "Arduino Uno")]),
            "COM9",
        )

    def test_single_port_is_selected(self):
        self.assertEqual(
            choose_serial_port(None, [("/dev/ttyACM0", "Arduino Uno")]),
            "/dev/ttyACM0",
        )

    def test_unique_arduino_port_is_preferred(self):
        available = [
            ("COM2", "Bluetooth link"),
            ("COM5", "Arduino Uno"),
        ]
        self.assertEqual(choose_serial_port(None, available), "COM5")

    def test_ambiguous_ports_require_manual_selection(self):
        with self.assertRaises(RuntimeError):
            choose_serial_port(
                None,
                [("COM2", "Serial"), ("COM3", "Serial")],
            )


if __name__ == "__main__":
    unittest.main()
