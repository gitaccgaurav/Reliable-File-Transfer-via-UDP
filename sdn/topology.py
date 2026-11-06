
#!/usr/bin/env python3
"""Mininet topology: 3 hosts, 4 switches, primary and backup path."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController

from net_config import HOSTS, SWITCH_LINKS, SWITCHES


def build(loss=0.0, bw=5.0, host_delay="1ms"):
    """Build network with optional packet loss and bandwidth."""

    net = Mininet(
        controller=None,
        switch=OVSKernelSwitch,
        link=TCLink
    )

    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653
    )

    sw = {
        d: net.addSwitch(
            f"s{d}",
            dpid=f"{d:016x}",
            protocols="OpenFlow13",
            failMode="secure"
        )
        for d in SWITCHES
    }

    for name, (ip, mac, dpid, port) in HOSTS.items():
        host = net.addHost(name, ip=f"{ip}/24", mac=mac)

        net.addLink(
            host,
            sw[dpid],
            port2=port,
            bw=bw,
            delay=host_delay
        )

    for a, pa, b, pb, _cost, delay in SWITCH_LINKS:
        params = {"bw": bw, "delay": delay}

        if a == 1 and loss:
            params["loss"] = loss

        net.addLink(
            sw[a],
            sw[b],
            port1=pa,
            port2=pb,
            **params
        )

    return net


if __name__ == "__main__":
    ap = argparse.ArgumentParser()

    ap.add_argument("--loss", type=float, default=0.0)
    ap.add_argument("--bw", type=float, default=5.0)

    args = ap.parse_args()

    setLogLevel("info")

    net = build(args.loss, args.bw)
    net.start()
    net.staticArp()

    CLI(net)
    net.stop()
