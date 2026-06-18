from __future__ import annotations

import queue
import sys
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from protocol import HelloFrame, MemoryFrame, SnapshotFrame  # noqa: E402
from simulator import SimulatorWorker  # noqa: E402


class SimulatorTests(unittest.TestCase):
    def test_simulator_emits_full_protocol(self):
        events = queue.Queue()
        simulator = SimulatorWorker(events, sample_hz=20)
        simulator.start()
        time.sleep(0.16)
        simulator.stop()

        frames = [
            event.data
            for event in list(events.queue)
            if event.kind == "frame"
        ]
        self.assertTrue(any(isinstance(frame, HelloFrame) for frame in frames))
        self.assertTrue(any(isinstance(frame, MemoryFrame) for frame in frames))

        snapshots = [
            frame for frame in frames if isinstance(frame, SnapshotFrame)
        ]
        self.assertGreaterEqual(len(snapshots), 2)
        self.assertEqual(len(snapshots[0].sram), 128)
        self.assertEqual(set(snapshots[0].ports), {"B", "C", "D"})


if __name__ == "__main__":
    unittest.main()
