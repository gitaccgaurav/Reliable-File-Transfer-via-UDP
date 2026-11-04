
"""Pure-Python path computation (no Ryu, no Mininet) so it can be unit-tested."""

import heapq

from net_config import HOSTS, SWITCH_LINKS, SWITCHES, link_id


def link_of(dpid, port):
    """Which switch-to-switch link is this (switch, port) the end of?
    None = host port.
    """
    for a, pa, b, pb, _w, _d in SWITCH_LINKS:
        if (dpid, port) in ((a, pa), (b, pb)):
            return link_id(a, b)
    return None


def _adjacency(down_links):
    adj = {d: [] for d in SWITCHES}

    for a, pa, b, pb, w, _d in SWITCH_LINKS:
        if link_id(a, b) in down_links:
            continue

        adj[a].append((b, pb, w))
        adj[b].append((a, pa, w))

    return adj


def next_hops(down_links=frozenset()):
    """{host: {dpid: out_port}} = for every switch,
    where to send traffic for each host.
    """
    adj = _adjacency(down_links)
    table = {}

    for host, (_ip, _mac, sw, host_port) in HOSTS.items():
        dist, hop = {sw: 0}, {sw: host_port}
        heap = [(0, sw)]

        while heap:
            d, u = heapq.heappop(heap)

            if d > dist[u]:
                continue

            for v, port_on_v_toward_u, w in adj[u]:
                if d + w < dist.get(v, float("inf")):
                    dist[v], hop[v] = d + w, port_on_v_toward_u
                    heapq.heappush(heap, (d + w, v))

        table[host] = hop

    return table


def path(src_host, dst_host, down_links=frozenset()):
    """List of switch dpids a packet crosses, or None if unreachable."""
    hops = next_hops(down_links)[dst_host]
    here = HOSTS[src_host][2]
    route = [here]

    while here != HOSTS[dst_host][2]:
        port = hops.get(here)
        nxt = None

        for a, pa, b, pb, _w, _d in SWITCH_LINKS:
            if link_id(a, b) in down_links:
                continue

            if (here, port) == (a, pa):
                nxt = b
            elif (here, port) == (b, pb):
                nxt = a

        if port is None or nxt is None or nxt in route:
            return None

        route.append(nxt)
        here = nxt

    return route


def path_str(route):
    return "-".join(f"s{d}" for d in route) if route else "UNREACHABLE"
