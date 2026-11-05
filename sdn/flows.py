
"""Helpers that turn a routing table into OpenFlow 1.3 flow entries."""

from net_config import HOSTS

ETH_IP, ETH_ARP = 0x0800, 0x0806
PRIORITY = 10


def add_flow(dp, priority, match, actions):
    ofp, parser = dp.ofproto, dp.ofproto_parser
    inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]

    # Same match + priority as an existing entry => OpenFlow REPLACES it.
    # That is how rerouting works: we simply "add" the new output port.
    dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                  instructions=inst))


def delete_flow(dp, priority, match):
    ofp, parser = dp.ofproto, dp.ofproto_parser
    dp.send_msg(parser.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE_STRICT,
                                  priority=priority, match=match,
                                  out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY))


def install_flows(dp, table):
    """table = routing.next_hops(...) -> {host: {dpid: out_port}}"""
    parser = dp.ofproto_parser

    for host, (ip, _mac, _sw, _port) in HOSTS.items():
        port = table[host].get(dp.id)

        ip_match = parser.OFPMatch(eth_type=ETH_IP, ipv4_dst=ip)
        arp_match = parser.OFPMatch(eth_type=ETH_ARP, arp_tpa=ip)

        if port is None:
            # Host unreachable from this switch
            delete_flow(dp, PRIORITY, ip_match)
            delete_flow(dp, PRIORITY, arp_match)
            continue

        actions = [parser.OFPActionOutput(port)]
        add_flow(dp, PRIORITY, ip_match, actions)
        add_flow(dp, PRIORITY, arp_match, actions)
