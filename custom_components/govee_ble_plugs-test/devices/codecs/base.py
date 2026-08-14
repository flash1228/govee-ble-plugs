"""Core Govee BLE frame primitives.

Single command frame, always 20 bytes:
    byte[0]  = command type   0x33 write / 0xAA read
    byte[1]  = opcode
    byte[2..18] = payload (zero-padded, 17 bytes)
    byte[19] = BCC = XOR of bytes[0..18]
"""
from __future__ import annotations

FRAME_LEN = 20

WRITE = 0x33   # single write / control
READ = 0xAA    # single read / query
NOTIFY = 0xEE  # device -> app notification
MULTI_WRITE = 0xA1
MULTI_READ = 0xA2


def xor_checksum(data: bytes) -> int:
    """BCC: XOR of every byte."""
    bcc = 0
    for b in data:
        bcc ^= b
    return bcc & 0xFF


def single_frame(cmd_type: int, opcode: int, payload: bytes = b"") -> bytes:
    """Build a 20-byte single-command frame with a trailing XOR checksum.

    Raises ValueError if the payload doesn't fit (header is 2 bytes, checksum 1 byte, so
    payload must be <= 17 bytes).
    """
    if len(payload) > FRAME_LEN - 3:
        raise ValueError(f"payload too long: {len(payload)} > {FRAME_LEN - 3}")
    body = bytes([cmd_type & 0xFF, opcode & 0xFF]) + bytes(payload)
    body = body.ljust(FRAME_LEN - 1, b"\x00")
    return body + bytes([xor_checksum(body)])


def is_valid_frame(frame: bytes) -> bool:
    """True if a 20-byte frame's trailing checksum is correct."""
    return len(frame) == FRAME_LEN and xor_checksum(frame[:-1]) == frame[-1]


def le16(value: int) -> bytes:
    """16-bit little-endian (scene / DIY codes)."""
    return bytes([value & 0xFF, (value >> 8) & 0xFF])


def be16(value: int) -> bytes:
    """16-bit big-endian (colour-temperature kelvin)."""
    return bytes([(value >> 8) & 0xFF, value & 0xFF])
