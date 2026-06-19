from __future__ import annotations

from dataclasses import dataclass

from protocol import (
    FLAG_CARRY,
    FLAG_DIV_ZERO,
    FLAG_NEGATIVE,
    FLAG_OVERFLOW,
    FLAG_ZERO,
)


@dataclass(frozen=True)
class UlaResult:
    result: int
    flags: int


def execute_ula(a: int, b: int, operation: int) -> UlaResult:
    if not 0 <= a <= 15 or not 0 <= b <= 15:
        raise ValueError("A e B devem ser valores de 4 bits.")
    if not 0 <= operation <= 7:
        raise ValueError("A operação deve estar entre 0 e 7.")

    result = 0
    carry = False
    overflow = False
    div_zero = False

    if operation == 0:
        result = a & b
    elif operation == 1:
        result = a | b
    elif operation == 2:
        result = (~b) & 0x0F
    elif operation == 3:
        result = a ^ b
    elif operation == 4:
        total = a + b
        carry = total > 15
        result = total & 0x0F
    elif operation == 5:
        carry = a < b
        result = (a - b) & 0x0F
    elif operation == 6:
        product = a * b
        overflow = product > 15
        carry = overflow
        result = product & 0x0F
    elif operation == 7:
        if b == 0:
            div_zero = True
            result = 0
        else:
            result = a // b

    flags = 0
    if result == 0:
        flags |= FLAG_ZERO
    if carry:
        flags |= FLAG_CARRY
    if result & 0x08:
        flags |= FLAG_NEGATIVE
    if overflow:
        flags |= FLAG_OVERFLOW
    if div_zero:
        flags |= FLAG_DIV_ZERO
    return UlaResult(result=result, flags=flags)
