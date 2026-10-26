"""End-to-end tests on localhost (no Mininet needed): loss, lost ACKs, integrity."""
import hashlib
import json
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class LoopbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.port = free_port()
        self.rx = None

    def tearDown(self):
        if self.rx:
            self.rx.terminate()
            self.rx.wait()

    def start_receiver(self, *extra):
        self.rx = subprocess.Popen(
            [sys.executable, "receiver.py", "--bind", "127.0.0.1", "--port", str(self.port),
             "--out-dir", self.tmp, *extra],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.4)

    def make_file(self, size):
        path = os.path.join(self.tmp, "input.bin")
        with open(path, "wb") as f:
            rng = random.Random(size)
            f.write(bytes(rng.getrandbits(8) for _ in range(size)))   # binary, not text
        return path

    def send(self, script, path, *extra):
        out = subprocess.run(
            [sys.executable, script, path, "127.0.0.1", "--port", str(self.port),
             "--no-notify", *extra], cwd=ROOT, capture_output=True, text=True, timeout=120)
        return json.loads(out.stdout.strip().splitlines()[-1])

    def received_hash(self, tid, name="input.bin"):
        with open(os.path.join(self.tmp, f"{tid}_{name}"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def check(self, script, size, *sender_args, receiver_args=()):
        self.start_receiver(*receiver_args)
        path = self.make_file(size)
        res = self.send(script, path, *sender_args)
        self.assertEqual(res["verdict"], "PASS", res)
        with open(path, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), self.received_hash(res["tid"]))
        return res

    def test_sw_clean(self):
        self.assertEqual(self.check("sender.py", 50_000)["retransmissions"], 0)

    def test_sw_packet_loss(self):
        self.assertGreater(self.check("sender.py", 30_000, "--drop-rate", "0.2")["retransmissions"], 0)

    def test_sw_lost_acks(self):
        res = self.check("sender.py", 30_000, receiver_args=("--drop-ack", "0.2"))
        self.assertGreater(res["retransmissions"], 0)

    def test_sr_clean(self):
        self.assertEqual(self.check("sender_sr.py", 200_000)["retransmissions"], 0)

    def test_sr_heavy_loss_both_directions(self):
        res = self.check("sender_sr.py", 100_000, "--drop-rate", "0.2",
                         receiver_args=("--drop-ack", "0.2"))
        self.assertGreater(res["retransmissions"], 0)

    def test_empty_file(self):
        self.check("sender.py", 0)

    def test_receiver_survives_garbage_datagram(self):
        self.start_receiver()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"\x00garbage" * 5, ("127.0.0.1", self.port))
        s.close()
        self.assertEqual(self.send("sender.py", self.make_file(5_000))["verdict"], "PASS")

    def test_two_senders_at_once(self):
        self.start_receiver()
        path = self.make_file(80_000)
        procs = [subprocess.Popen(
            [sys.executable, s, path, "127.0.0.1", "--port", str(self.port), "--no-notify"],
            cwd=ROOT, stdout=subprocess.PIPE, text=True) for s in ("sender.py", "sender_sr.py")]
        for p in procs:
            out, _ = p.communicate(timeout=120)
            self.assertEqual(json.loads(out.strip().splitlines()[-1])["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()