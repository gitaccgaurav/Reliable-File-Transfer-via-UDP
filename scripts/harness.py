"""Shared helpers for run_demo.py and run_experiments.py."""

import glob
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "sdn"))

import protocol as P
from topology import build

SENDERS = {"sw": "sender.py", "sr": "sender_sr.py"}


def start_network(loss=0.0, bw=5.0, settle=4):
    net = build(loss=loss, bw=bw)
    net.start()
    net.staticArp()
    time.sleep(settle)
    return net


def link_down(net, a="s1", b="s2"):
    net.configLinkStatus(a, b, "down")


def link_up(net, a="s1", b="s2"):
    net.configLinkStatus(a, b, "up")


def blackhole_on(net, sw="s2"):
    """Silently drop IP traffic while the port remains UP."""
    net.get(sw).cmd(
        f"ovs-ofctl -O OpenFlow13 add-flow {sw} 'priority=100,ip,actions=drop'"
    )


def blackhole_off(net, sw="s2"):
    net.get(sw).cmd(
        f"ovs-ofctl -O OpenFlow13 --strict del-flows {sw} 'priority=100,ip'"
    )


def dump_flows(net, switches=("s1", "s2", "s3")):
    for s in switches:
        print(f"--- flow table of {s}")
        print(net.get(s).cmd(f"ovs-ofctl -O OpenFlow13 dump-flows {s}"))


def run_transfer(net, path, sender="sr", src="h1",
                 events=(), extra=(), timeout=300):

    rx_dir = os.path.join(ROOT, "received_files")
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)

    rx_log = open(
        os.path.join(ROOT, "logs", "receiver_mininet.log"), "a"
    )

    rx = net.get("h2").popen(
        ["python3", "receiver.py", "--out-dir", rx_dir],
        cwd=ROOT,
        stdout=rx_log,
        stderr=subprocess.STDOUT
    )

    time.sleep(1)

    out = tempfile.NamedTemporaryFile(
        "w+", suffix=".log", delete=False
    )

    cmd = [
        "python3", SENDERS[sender], path,
        "10.0.0.2", "--name", src, *extra
    ]

    t0 = time.time()

    tx = net.get(src).popen(
        cmd,
        cwd=ROOT,
        stdout=out,
        stderr=subprocess.STDOUT
    )

    pending = sorted(events, key=lambda e: e[0])

    while tx.poll() is None and time.time() - t0 < timeout:
        while pending and time.time() - t0 >= pending[0][0]:
            _, label, fn = pending.pop(0)
            print(
                f"[{time.time() - t0:6.2f}s] EVENT: {label}",
                flush=True
            )
            fn()

        time.sleep(0.05)

    if tx.poll() is None:
        tx.kill()

    rx.terminate()

    out.flush()
    out.seek(0)

    lines = [
        line for line in out.read().splitlines()
        if line.strip()
    ]

    print(
        "\n".join(
            line for line in lines[:-1]
            if "TIMEOUT" in line
            or "RETRANSMIT" in line
            or "told SDN" in line
            or "FAILED" in line
        )[-3000:]
    )

    try:
        result = json.loads(lines[-1])
    except (ValueError, IndexError):
        return {
            "verdict": "ERROR",
            "error": "sender printed no result",
            "harness_verified": False
        }

    match = glob.glob(
        os.path.join(rx_dir, f"{result['tid']}_*")
    )

    result["harness_verified"] = (
        bool(match)
        and P.sha256_file(match[0]) == P.sha256_file(path)
    )

    return result
