"""Packet format shared by sender and receiver.

Header (15 bytes, network byte order):
type(1) | transfer_id(4) | seq(4) | payload_len(2) | crc32(4)
"""

import hashlib
import struct
import zlib
from collections import namedtuple

# Message types
START, DATA, ACK, FIN, FIN_ACK = 1, 2, 3, 4, 5

NAMES = {
    START: "START",
    DATA: "DATA",
    ACK: "ACK",
    FIN: "FIN",
    FIN_ACK: "FIN_ACK",
}

# Packet header: 15 bytes
HEADER = struct.Struct("!BIIHI")
HEADER_SIZE = HEADER.size

# START metadata: file size, chunk count, SHA-256 digest
START_BODY = struct.Struct("!QI32s")

Packet = namedtuple("Packet", "ptype tid seq payload")

def _crc(ptype, tid, seq, payload):
    header = HEADER.pack(ptype, tid, seq, len(payload), 0)
    return zlib.crc32(header + payload) & 0xFFFFFFFF

def pack(ptype, tid, seq, payload=b""):
    crc = _crc(ptype, tid, seq, payload)
    header = HEADER.pack(ptype, tid, seq, len(payload), crc)
    return header + payload

def unpack(data):
    """Return a Packet, or None if the packet is invalid."""
    if len(data) < HEADER_SIZE:
        return None

    ptype, tid, seq, length, crc = HEADER.unpack(data[:HEADER_SIZE])
    payload = data[HEADER_SIZE:]

    if ptype not in NAMES or len(payload) != length:
        return None

    if _crc(ptype, tid, seq, payload) != crc:
        return None

    return Packet(ptype, tid, seq, payload)

def pack_start(file_size, total_chunks, digest, filename):
    return START_BODY.pack(
        file_size, total_chunks, digest
    ) + filename.encode()

def unpack_start(payload):
    if len(payload) < START_BODY.size:
        raise ValueError("Invalid START payload")

    size, total, digest = START_BODY.unpack(
        payload[:START_BODY.size]
    )
    filename = payload[START_BODY.size:].decode(errors="replace")

    return size, total, digest, filename

def split_file(data, chunk_size):
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    return [
        data[i:i + chunk_size]
        for i in range(0, len(data), chunk_size)
    ]

def sha256_file(path):
    h = hashlib.sha256()

    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)

    return h.hexdigest()
