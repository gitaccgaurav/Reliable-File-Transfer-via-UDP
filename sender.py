#!/usr/bin/env python3
"""Reliable-UDP file sender, D1 version: stop-and-wait ARQ."""

import argparse
import hashlib
import json
import os
import random
import socket
import sys
import time

import config
import protocol as P
from notify import notify_controller


class TransferError(Exception):
    pass


def log(msg):
    t = time.time()
    print(
        f"[{time.strftime('%H:%M:%S', time.localtime(t))}."
        f"{int(t * 1000) % 1000:03d}] {msg}",
        flush=True
    )


class Stats:
    def __init__(self):
        self.sent = self.retx = self.timeouts = self.sim_drops = 0
        self.consecutive = 0
        self.last_progress = time.time()
        self.max_gap = 0.0
        self.last_notify = 0.0

    def progress(self):
        now = time.time()
        self.max_gap = max(self.max_gap, now - self.last_progress)
        self.last_progress = now
        self.consecutive = 0


class Ctx:
    """Everything one transfer needs: socket, destination, ids, counters."""

    def __init__(self, sock, addr, tid, args):
        self.sock, self.addr, self.tid, self.args = sock, addr, tid, args
        self.stats = Stats()

    def transmit(self, ptype, seq, pkt, retx=False):
        st = self.stats
        st.sent += 1
        st.retx += 1 if retx else 0

        if self.args.verbose or retx:
            log(f"{P.NAMES[ptype]} seq={seq} "
                f"{'RETRANSMIT' if retx else 'sent'}")

        if random.random() < self.args.drop_rate:
            st.sim_drops += 1
            return

        self.sock.sendto(pkt, self.addr)

    def maybe_notify(self):
        st, a = self.stats, self.args
        now = time.time()

        if (a.no_notify or st.consecutive < config.NOTIFY_AFTER
                or now - st.last_notify < 3):
            return

        st.last_notify = now
        sent = notify_controller(
            "path_problem",
            src=a.name,
            dst_ip=self.addr[0],
            timeouts=st.consecutive
        )

        log(f"{st.consecutive} consecutive timeouts -> told SDN controller "
            f"({'delivered' if sent else 'no controller listening'})")


def send_reliable(ctx, ptype, seq, payload, expect_type):
    """Send one packet and wait for its matching reply."""
    pkt = P.pack(ptype, ctx.tid, seq, payload)

    for attempt in range(config.MAX_RETRIES + 1):
        ctx.transmit(ptype, seq, pkt, retx=attempt > 0)
        deadline = time.time() + config.TIMEOUT

        while True:
            remaining = deadline - time.time()

            if remaining <= 0:
                break

            ctx.sock.settimeout(remaining)

            try:
                data, _ = ctx.sock.recvfrom(2048)
            except socket.timeout:
                break

            r = P.unpack(data)

            if (r and r.ptype == expect_type
                    and r.tid == ctx.tid and r.seq == seq):
                ctx.stats.progress()
                return r

        ctx.stats.timeouts += 1
        ctx.stats.consecutive += 1

        log(f"TIMEOUT waiting for {P.NAMES[expect_type]} "
            f"of seq={seq} (attempt {attempt + 1})")

        ctx.maybe_notify()

    raise TransferError(
        f"gave up on {P.NAMES[ptype]} seq={seq} "
        f"after {config.MAX_RETRIES} retries"
    )


def stop_and_wait(ctx, chunks):
    for seq, chunk in enumerate(chunks):
        send_reliable(ctx, P.DATA, seq, chunk, P.ACK)


def build_parser(desc):
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("file")
    ap.add_argument("host", help="receiver IP address")
    ap.add_argument("--port", type=int, default=config.PORT)
    ap.add_argument("--name", default="sender",
                    help="host label sent to the controller")
    ap.add_argument("--drop-rate", type=float, default=0.0)
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--stats-file")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def run(args, transfer_fn, label):
    with open(args.file, "rb") as f:
        data = f.read()

    chunks = P.split_file(data, config.CHUNK_SIZE)
    digest = hashlib.sha256(data).digest()
    tid = random.getrandbits(32)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ctx = Ctx(sock, (args.host, args.port), tid, args)

    verdict, error, t0 = "ERROR", None, time.time()

    try:
        body = P.pack_start(
            len(data), len(chunks), digest,
            os.path.basename(args.file)
        )

        send_reliable(ctx, P.START, 0, body, P.ACK)

        log(f"transfer {tid}: {len(data)} bytes in {len(chunks)} chunks, "
            f"sha256={digest.hex()[:16]}...")

        transfer_fn(ctx, chunks)

        verdict = send_reliable(
            ctx, P.FIN, 0, b"", P.FIN_ACK
        ).payload.decode()

    except TransferError as e:
        error = str(e)
        log(f"TRANSFER FAILED: {error}")

    finally:
        sock.close()

    elapsed = time.time() - t0
    st = ctx.stats

    result = {
        "protocol": label,
        "tid": tid,
        "file": os.path.basename(args.file),
        "bytes": len(data),
        "chunks": len(chunks),
        "elapsed_s": round(elapsed, 3),
        "throughput_kBps": round(
            len(data) / 1000 / elapsed, 1
        ) if elapsed else 0,
        "packets_sent": st.sent,
        "retransmissions": st.retx,
        "timeouts": st.timeouts,
        "max_ack_gap_s": round(st.max_gap, 3),
        "verdict": verdict,
        "error": error
    }

    log(f"RESULT receiver integrity check: {verdict}")
    print(json.dumps(result), flush=True)

    if args.stats_file:
        with open(args.stats_file, "a") as f:
            f.write(json.dumps(result) + "\n")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(
        run(
            build_parser("Reliable UDP sender (stop-and-wait)").parse_args(),
            stop_and_wait,
            "stop-and-wait"
        )
    )
