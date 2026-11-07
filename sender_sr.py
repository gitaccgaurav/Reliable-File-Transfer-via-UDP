#!/usr/bin/env python3
"""Reliable-UDP file sender: Selective Repeat with adaptive timeout."""

import socket
import sys
import time

import config
import protocol as P
from sender import TransferError, build_parser, log, run


def selective_repeat(ctx, chunks, window):
    total = len(chunks)

    acked = [False] * total
    sent_at = {}
    tries = {}

    base = 0
    nxt = 0

    srtt = None
    rttvar = None
    rto = config.RTO_INIT

    pkts = [
        P.pack(P.DATA, ctx.tid, i, chunk)
        for i, chunk in enumerate(chunks)
    ]

    def transmit(seq):
        tries[seq] = tries.get(seq, 0) + 1
        sent_at[seq] = time.time()

        ctx.transmit(
            P.DATA,
            seq,
            pkts[seq],
            retx=tries[seq] > 1
        )

    while base < total:

        # 1. Fill the sending window
        while nxt < total and nxt < base + window:
            transmit(nxt)
            nxt += 1

        # 2. Wait for the earliest pending packet timeout
        pending = [
            s for s in range(base, nxt)
            if not acked[s]
        ]

        wait = max(
            0.001,
            min(sent_at[s] + rto for s in pending) - time.time()
        )

        ctx.sock.settimeout(wait)

        try:
            data, _ = ctx.sock.recvfrom(2048)
            r = P.unpack(data)

            if (
                r
                and r.ptype == P.ACK
                and r.tid == ctx.tid
                and 0 <= r.seq < total
                and not acked[r.seq]
            ):
                acked[r.seq] = True
                ctx.stats.progress()

                # Karn's rule: use RTT only for packets sent once
                if tries[r.seq] == 1:
                    rtt = time.time() - sent_at[r.seq]

                    if srtt is None:
                        srtt = rtt
                        rttvar = rtt / 2
                    else:
                        rttvar = (
                            0.75 * rttvar
                            + 0.25 * abs(srtt - rtt)
                        )

                        srtt = (
                            0.875 * srtt
                            + 0.125 * rtt
                        )

                    rto = min(
                        config.RTO_MAX,
                        max(config.RTO_MIN, srtt + 4 * rttvar)
                    )

                # Slide the window over consecutive ACKed packets
                while base < total and acked[base]:
                    base += 1

        except socket.timeout:
            pass

        # 3. Retransmit expired packets
        now = time.time()

        expired = [
            s for s in range(base, nxt)
            if not acked[s] and now - sent_at[s] >= rto
        ]

        if expired:
            ctx.stats.consecutive += 1
            ctx.stats.timeouts += len(expired)

            rto = min(config.RTO_MAX, rto * 2)

            log(
                f"TIMEOUT {len(expired)} packet(s), "
                f"first seq={expired[0]}, rto -> {rto:.2f}s"
            )

            for s in expired:
                if tries[s] > config.MAX_RETRIES:
                    raise TransferError(
                        f"gave up on DATA seq={s} "
                        f"after {config.MAX_RETRIES} retries"
                    )

                transmit(s)

            ctx.maybe_notify()


if __name__ == "__main__":
    ap = build_parser("Reliable UDP sender (selective repeat)")
    ap.add_argument(
        "--window",
        type=int,
        default=config.WINDOW_SIZE
    )

    args = ap.parse_args()

    sys.exit(
        run(
            args,
            lambda ctx, chunks: selective_repeat(
                ctx, chunks, args.window
            ),
            "selective-repeat"
        )
    )
