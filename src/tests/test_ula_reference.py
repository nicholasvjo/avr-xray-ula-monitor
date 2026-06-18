from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from protocol import (  # noqa: E402
    FLAG_CARRY,
    FLAG_DIV_ZERO,
    FLAG_NEGATIVE,
    FLAG_OVERFLOW,
    FLAG_ZERO,
)
from ula_reference import execute_ula  # noqa: E402


class UlaReferenceTests(unittest.TestCase):
    def test_all_4_bit_inputs_and_operations(self):
        for a in range(16):
            for b in range(16):
                for operation in range(8):
                    with self.subTest(a=a, b=b, operation=operation):
                        actual = execute_ula(a, b, operation)
                        expected_result, expected_flags = self._expected(
                            a, b, operation
                        )
                        self.assertEqual(actual.result, expected_result)
                        self.assertEqual(actual.flags, expected_flags)

    @staticmethod
    def _expected(a: int, b: int, operation: int) -> tuple[int, int]:
        carry = False
        overflow = False
        div_zero = False

        if operation == 0:
            result = a & b
        elif operation == 1:
            result = a | b
        elif operation == 2:
            result = 15 - b
        elif operation == 3:
            result = a ^ b
        elif operation == 4:
            carry = a + b >= 16
            result = (a + b) % 16
        elif operation == 5:
            carry = a < b
            result = (a - b) % 16
        elif operation == 6:
            overflow = a * b >= 16
            carry = overflow
            result = (a * b) % 16
        else:
            div_zero = b == 0
            result = 0 if div_zero else a // b

        flags = 0
        if result == 0:
            flags |= FLAG_ZERO
        if carry:
            flags |= FLAG_CARRY
        if result >= 8:
            flags |= FLAG_NEGATIVE
        if overflow:
            flags |= FLAG_OVERFLOW
        if div_zero:
            flags |= FLAG_DIV_ZERO
        return result, flags


if __name__ == "__main__":
    unittest.main()
