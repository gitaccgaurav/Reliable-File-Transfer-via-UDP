#!/usr/bin/env python3
"""Automated experiments -> results/experiments.csv. Run with sudo.
	sudo python3 scripts/run_experiments.py --suite loss
	# terminal 1: ryu-manager sdn/controller.py then:
	sudo python3 scripts/run_experiments.py --suite failure --tag sdn
	# restart controller as: REROUTE=0 ryu-manager sdn/controller.py then:
	sudo python3 scripts/run_experiments.py --suite failure --tag static
"""
import argparse
import csv
import os

import harness as H

CSV_PATH = os.path.join(H.ROOT, "results", "experiments.csv")
FIELDS = ["suite", "tag", "sender", "loss", "bw", "trial", "bytes", "elapsed_s",
		  "throughput_kBps", "packets_sent", "retransmissions", "timeouts",
		  "max_ack_gap_s", "verdict", "harness_verified"]

LOSS_LEVELS = [0, 2, 5, 10]
LOSS_FILE_KB = 300
# (file KB, bandwidth Mbit/s, link down at s, link up at s) - tune so a run lasts >= 10 s
FAILURE_PLAN = {"sr": (2000, 2, 3.0, 8.0), "sw": (200, 5, 1.5, 5.0)}

def sample(kb):
	path = os.path.join(H.ROOT, "sample_files", f"{kb}KB.bin")
	if not os.path.exists(path):
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "wb") as f:
			f.write(os.urandom(kb * 1000))
	return path


def record(row):
	os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
	new = not os.path.exists(CSV_PATH)
	with open(CSV_PATH, "a", newline="") as f:
		w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
		if new:
			w.writeheader()
		w.writerow(row)


def loss_suite(trials):
	for loss in LOSS_LEVELS:
		net = H.start_network(loss=loss, bw=5)
		for sender in ("sw", "sr"):
			for t in range(1, trials + 1):
				print(f"\n### loss={loss}% sender={sender} trial={t}")
				res = H.run_transfer(net, sample(LOSS_FILE_KB), sender, extra=["--no-notify"])
				record({"suite": "loss", "tag": "-", "sender": sender, "loss": loss, "bw": 5,
						"trial": t, **res})
		net.stop()
		
		
def failure_suite(tag, trials):
	for sender, (kb, bw, down_at, up_at) in FAILURE_PLAN.items():
		for t in range(1, trials + 1):
			net = H.start_network(loss=0, bw=bw)
			print(f"\n### failure tag={tag} sender={sender} trial={t}")
			events = [(down_at, "s1-s2 DOWN", lambda: H.link_down(net)),
					  (up_at, "s1-s2 UP", lambda: H.link_up(net))]
			res = H.run_transfer(net, sample(kb), sender, events=events)
			record({"suite": "failure", "tag": tag, "sender": sender, "loss": 0, "bw": bw,
					"trial": t, **res})
			net.stop()


if __name__ == "__main__":
	ap = argparse.ArgumentParser()
	ap.add_argument("--suite", choices=["loss", "failure"], required=True)
	ap.add_argument("--tag", default="sdn", help="label for the failure suite: sdn or static")
	ap.add_argument("--trials", type=int, default=3)
	a = ap.parse_args()
	loss_suite(a.trials) if a.suite == "loss" else failure_suite(a.tag, a.trials)