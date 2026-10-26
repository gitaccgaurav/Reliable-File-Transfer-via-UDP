#!/usr/bin/env python3
"""Reliable-UDP file receiver.

One UDP socket serves many senders at once: every datagram is routed to a
Session object chosen by (sender address, transfer id).
"""
import argparse
import hashlib
import json
import os
import random
import socket
import struct
import time

import config
import protocol as P


def log(msg):
    t = time.time()
    print(f"[{time.strftime('%H:%M:%S', time.localtime(t))}.{int(t * 1000) % 1000:03d}] {msg}",
          flush=True)


class Session:
    def __init__(self, addr, tid, size, total, digest, name):
        self.addr, self.tid = addr, tid
        self.size, self.total, self.digest = size, total, digest
        self.name = os.path.basename(name) or "file.bin"   # never trust a path from the network
        self.chunks = {}            # seq -> bytes (this dict is how we reorder)
        self.next_needed = 0        # lowest seq we have not received yet
        self.duplicates = 0
        self.out_of_order = 0
        self.done = False
        self.result = b""
        self.t0 = time.time()


def send(sock, addr, ptype, tid, seq, payload=b"", drop=0.0):
    if random.random() < drop:
        log(f"(simulated loss) {P.NAMES[ptype]} seq={seq} NOT sent")
        return
    sock.sendto(P.pack(ptype, tid, seq, payload), addr)


def on_start(sock, addr, pkt, sessions, args):
    key = (addr, pkt.tid)
    if key not in sessions:
        try:
            size, total, digest, name = P.unpack_start(pkt.payload)
        except struct.error:
            log("malformed START ignored")
            return
        sessions[key] = Session(addr, pkt.tid, size, total, digest, name)
        log(f"START tid={pkt.tid} from {addr[0]}:{addr[1]} file={name!r} "
            f"size={size} chunks={total}")
    else:
        log(f"duplicate START tid={pkt.tid} -> re-ACK")
    send(sock, addr, P.ACK, pkt.tid, 0, drop=args.drop_ack)


def on_data(sock, addr, pkt, sessions, args):
    s = sessions.get((addr, pkt.tid))
    if s is None or pkt.seq >= s.total:
        log(f"DATA seq={pkt.seq} for unknown transfer {pkt.tid} ignored")
        return
    if s.done or pkt.seq in s.chunks:
        s.duplicates += 1
        log(f"DUP seq={pkt.seq} ignored (not written twice) -> re-ACK")
    else:
        if pkt.seq > s.next_needed:
            s.out_of_order += 1
            log(f"GAP expected seq={s.next_needed}, got seq={pkt.seq}")
        s.chunks[pkt.seq] = pkt.payload
        while s.next_needed in s.chunks:
            s.next_needed += 1
        if args.verbose:
            log(f"DATA seq={pkt.seq} stored")
    send(sock, addr, P.ACK, pkt.tid, pkt.seq, drop=args.drop_ack)


def on_fin(sock, addr, pkt, sessions, args):
    s = sessions.get((addr, pkt.tid))
    if s is None:
        return
    if not s.done:
        missing = [i for i in range(s.total) if i not in s.chunks]
        if missing:
            log(f"FIN but {len(missing)} chunks MISSING (first: {missing[:10]})")
            return                                   # no FIN_ACK: sender must fix it
        data = b"".join(s.chunks[i] for i in range(s.total))
        ok = len(data) == s.size and hashlib.sha256(data).digest() == s.digest
        os.makedirs(args.out_dir, exist_ok=True)
        path = os.path.join(args.out_dir, f"{s.tid}_{s.name}")
        with open(path, "wb") as f:
            f.write(data)
        s.result, s.done, s.chunks = (b"PASS" if ok else b"FAIL"), True, {}
        elapsed = time.time() - s.t0
        log(f"INTEGRITY: {s.result.decode()}  file={path} bytes={len(data)} "
            f"dups={s.duplicates} out_of_order={s.out_of_order} time={elapsed:.2f}s")
        os.makedirs(config.LOG_DIR, exist_ok=True)
        with open(os.path.join(config.LOG_DIR, "receiver_summary.jsonl"), "a") as f:
            f.write(json.dumps({"tid": s.tid, "file": s.name, "bytes": len(data),
                                "result": s.result.decode(), "duplicates": s.duplicates,
                                "out_of_order": s.out_of_order,
                                "corrupt_dropped": args.corrupt_count[0]}) + "\n")
    send(sock, addr, P.FIN_ACK, pkt.tid, 0, s.result, drop=args.drop_ack)


def main():
    ap = argparse.ArgumentParser(description="Reliable UDP file receiver")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=config.PORT)
    ap.add_argument("--out-dir", default=config.RECV_DIR)
    ap.add_argument("--drop-ack", type=float, default=0.0,
                    help="probability of silently dropping an outgoing ACK (testing)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    args.corrupt_count = [0]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    log(f"receiver listening on {args.bind}:{args.port}")

    sessions = {}
    handlers = {P.START: on_start, P.DATA: on_data, P.FIN: on_fin}
    while True:
        data, addr = sock.recvfrom(65535)
        pkt = P.unpack(data)
        if pkt is None:
            args.corrupt_count[0] += 1
            log("CORRUPT/malformed datagram dropped")
            continue
        handler = handlers.get(pkt.ptype)
        if handler:
            handler(sock, addr, pkt, sessions, args)


if __name__ == "__main__":
    main()