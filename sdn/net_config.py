"""Single source of truth for the network layout.
topology.py builds Mininet from it; controller.py/routing.py route over it."""
# host: (ip, mac, switch dpid, port on that switch)
HOSTS = {
"h1": ("10.0.0.1", "00:00:00:00:00:01", 1, 1),
"h2": ("10.0.0.2", "00:00:00:00:00:02", 4, 3),
"h3": ("10.0.0.3", "00:00:00:00:00:03", 1, 4),
}
# (dpidA, portA, dpidB, portB, routing cost, one-way delay)
# h1,h3 h2
# | s2 (primary) |
# s1 ---< >--- s4
# s3 (backup)
SWITCH_LINKS = [
    (1, 2, 2, 1, 1, "2ms"), # s1-s2 primary
    (2, 2, 4, 1, 1, "2ms"), # s2-s4 primary
    (1, 3, 3, 1, 5, "10ms"), # s1-s3 backup (costlier, slower)
    (3, 2, 4, 2, 5, "10ms"), # s3-s4 backup
]
SWITCHES = [1, 2, 3, 4]

def link_id(a, b):
    return frozenset((a, b))
