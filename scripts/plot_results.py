#!/usr/bin/env python3
"""results/experiments.csv -> PNG graphs in results/. """
import csv
import os
import statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "results", "experiments.csv")


def load():
	with open(CSV_PATH) as f:
		return [r for r in csv.DictReader(f) if r["verdict"] == "PASS"]
		
		
def mean_by(rows, keyfn, valfn):
	groups = defaultdict(list)
	for r in rows:
		groups[keyfn(r)].append(float(valfn(r)))
	return {k: (st.mean(v), st.pstdev(v)) for k, v in groups.items()}

def grouped_bars(ax, data, categories, series, title, ylabel):
	width = 0.8 / max(len(series), 1)
	for i, s in enumerate(series):
		xs = [j + i * width for j in range(len(categories))]
		ys = [data.get((s, c), (0, 0))[0] for c in categories]
		es = [data.get((s, c), (0, 0))[1] for c in categories]
		ax.bar(xs, ys, width, yerr=es, capsize=3, label=s)
	ax.set_xticks([j + width * (len(series) - 1) / 2 for j in range(len(categories))])
	ax.set_xticklabels(categories)
	ax.set_title(title)
	ax.set_ylabel(ylabel)
	ax.legend()
	ax.grid(axis="y", alpha=0.3)


def main():
	rows = load()
	loss = [r for r in rows if r["suite"] == "loss"]
	fail = [r for r in rows if r["suite"] == "failure"]
	if loss:
		cats = sorted({r["loss"] for r in loss}, key=float)
		fig, axes = plt.subplots(1, 3, figsize=(15, 4))
		for ax, (field, title, yl) in zip(axes, [
				("throughput_kBps", "Throughput vs packet loss", "kB/s"),
				("retransmissions", "Retransmissions vs packet loss", "packets"),
				("elapsed_s", "Transfer time vs packet loss", "seconds")]):
			data = mean_by(loss, lambda r: (r["sender"], r["loss"]), lambda r, f=field: r[f])
			grouped_bars(ax, data, cats, ["sw", "sr"], title, yl)
			ax.set_xlabel("loss per direction (%)")
		fig.tight_layout()
		fig.savefig(os.path.join(ROOT, "results", "loss_comparison.png"), dpi=150)
	if fail:
		tags = sorted({r["tag"] for r in fail})
		fig, axes = plt.subplots(1, 2, figsize=(10, 4))
		for ax, (field, title, yl) in zip(axes, [
				("max_ack_gap_s", "Longest stall seen by the app", "seconds"),
				("elapsed_s", "Total transfer time with a link failure", "seconds")]):
			data = mean_by(fail, lambda r: (r["tag"], r["sender"]), lambda r, f=field: r[f])
			grouped_bars(ax, data, ["sw", "sr"], tags, title, yl)
		fig.tight_layout()
		fig.savefig(os.path.join(ROOT, "results", "failure_comparison.png"), dpi=150)
	print("graphs written to results/")
	
if __name__ == "__main__":
	main()