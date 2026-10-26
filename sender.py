#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import random
import socket
import time

import config
import protocol as P
from notify import notify_controller


def log(message, verbose=False):
    if verbose:
        print(message, flush=True)


def wait_for_packet(sock, expected_type, tid, expected_seq):
    sock.settimeout(config.TIMEOUT)
    start_time = time.monotonic()

    while True:
        remaining = config.TIMEOUT - (time.monotonic() - start_time)

        if remaining <= 0:
            return None

        sock.settimeout(remaining)

        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            return None

        packet = P.unpack(data)

        if packet is None:
            continue

        if packet.ptype != expected_type:
            continue

        if packet.tid != tid:
            continue

        if packet.seq != expected_seq:
            continue

        return packet


def send_reliably(sock, receiver, tid, ptype, seq, payload,
                  stats, drop_rate, verbose):
    retries = 0

    while True:
        # Simulate packet loss for testing.
        if random.random() < drop_rate:
            log(
                f"Simulated loss: {P.NAMES[ptype]} seq={seq}",
                verbose
            )
        else:
            sock.sendto(
                P.pack(ptype, tid, seq, payload),
                receiver
            )

        stats["packets_sent"] += 1

        packet = wait_for_packet(sock, P.ACK, tid, seq)

        if packet is not None:
            return True

        if retries >= config.MAX_RETRIES:
            return False

        retries += 1
        stats["retries"] += 1

        log(
            f"Timeout: {P.NAMES[ptype]} seq={seq}, retry {retries}",
            verbose
        )

        notify_controller(tid, seq, retries)


def send_file(file_path, host, port, name=None,
              drop_rate=0.0, stats_file=None, verbose=False):

    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    if not 0.0 <= drop_rate <= 1.0:
        raise ValueError("--drop-rate must be between 0 and 1")

    with open(file_path, "rb") as file:
        file_data = file.read()

    chunks = P.split_file(file_data, config.CHUNK_SIZE)
    digest = hashlib.sha256(file_data).digest()
    tid = random.randint(1, 2**32 - 1)
    receiver = (host, port)

    stats = {
        "tid": tid,
        "file": name or os.path.basename(file_path),
        "bytes": len(file_data),
        "packets_sent": 0,
        "retries": 0,
        "duration_seconds": 0,
        "success": False
    }

    start_time = time.monotonic()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:

            start_payload = P.pack_start(
                len(file_data),
                len(chunks),
                digest,
                name or os.path.basename(file_path)
            )

            if not send_reliably(
                sock, receiver, tid, P.START, 0,
                start_payload, stats, drop_rate, verbose
            ):
                raise TimeoutError("No ACK received for START")

            for seq, chunk in enumerate(chunks):
                if not send_reliably(
                    sock, receiver, tid, P.DATA, seq,
                    chunk, stats, drop_rate, verbose
                ):
                    raise TimeoutError(
                        f"No ACK received for DATA seq={seq}"
                    )

            retries = 0

            while True:
                if random.random() < drop_rate:
                    log("Simulated loss: FIN", verbose)
                else:
                    sock.sendto(P.pack(P.FIN, tid, 0), receiver)

                stats["packets_sent"] += 1

                packet = wait_for_packet(
                    sock, P.FIN_ACK, tid, 0
                )

                if packet is not None:
                    if packet.payload != b"PASS":
                        raise RuntimeError(
                            "Receiver reported integrity failure"
                        )

                    stats["success"] = True
                    break

                if retries >= config.MAX_RETRIES:
                    raise TimeoutError("No FIN_ACK received")

                retries += 1
                stats["retries"] += 1

                log(f"Timeout: FIN, retry {retries}", verbose)
                notify_controller(tid, 0, retries)

    except Exception as error:
        stats["error"] = str(error)

    finally:
        stats["duration_seconds"] = round(
            time.monotonic() - start_time, 3
        )

        if stats_file:
            directory = os.path.dirname(stats_file)
            if directory:
                os.makedirs(directory, exist_ok=True)

            with open(stats_file, "a") as file:
                file.write(json.dumps(stats) + "\n")

        print(json.dumps(stats), flush=True)

    return stats["success"]


def main():
    parser = argparse.ArgumentParser(
        description="Reliable UDP file sender"
    )

    parser.add_argument("file")
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--name", default=None)
    parser.add_argument("--drop-rate", type=float, default=0.0)
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--stats-file", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.no_notify:
        global notify_controller
        notify_controller = lambda tid, seq, retries: False

    success = send_file(
        args.file,
        args.host,
        args.port,
        args.name,
        args.drop_rate,
        args.stats_file,
        args.verbose
    )

    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

