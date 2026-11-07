"""One demonstration run inside Mininet.

D1 example:
sudo python3 scripts/run_demo.py sample_files/300KB.bin --sender sw --loss 5

D2 example:
sudo python3 scripts/run_demo.py sample_files/2MB.bin --sender sr --bw 2 --fail-at 3 --recover-at 8
"""

import argparse
import json
import harness as H


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("file")
    ap.add_argument("--sender", choices=["sw", "sr"], default="sw")
    ap.add_argument("--loss", type=float, default=0.0)
    ap.add_argument("--bw", type=float, default=5.0)

    ap.add_argument(
        "--fail-at",
        type=float,
        help="seconds after start: bring s1-s2 down"
    )

    ap.add_argument(
        "--recover-at",
        type=float,
        help="seconds after start: bring s1-s2 up"
    )

    ap.add_argument(
        "--blackhole-at",
        type=float,
        help="silently drop traffic at s2"
    )

    ap.add_argument(
        "--unblackhole-at",
        type=float
    )

    ap.add_argument(
        "--cli",
        action="store_true",
        help="open the Mininet CLI afterwards"
    )

    a = ap.parse_args()

    net = H.start_network(a.loss, a.bw)

    print("== connectivity check ==")
    net.pingAll()
    H.dump_flows(net, ("s1",))

    events = []

    if a.fail_at is not None:
        events.append(
            (a.fail_at, "LINK s1-s2 DOWN",
             lambda: H.link_down(net))
        )

    if a.recover_at is not None:
        events.append(
            (a.recover_at, "LINK s1-s2 UP",
             lambda: H.link_up(net))
        )

    if a.blackhole_at is not None:
        events.append(
            (a.blackhole_at, "BLACKHOLE at s2",
             lambda: H.blackhole_on(net))
        )

    if a.unblackhole_at is not None:
        events.append(
            (a.unblackhole_at, "BLACKHOLE removed",
             lambda: H.blackhole_off(net))
        )

    print("== transfer ==")

    res = H.run_transfer(
        net,
        a.file,
        a.sender,
        events=events
    )

    print("== result ==")
    print(json.dumps(res, indent=2))

    print("== flow tables after the run (compare with before) ==")
    H.dump_flows(net)

    if a.cli:
        from mininet.cli import CLI
        CLI(net)

    net.stop()


if __name__ == "__main__":
    main()
