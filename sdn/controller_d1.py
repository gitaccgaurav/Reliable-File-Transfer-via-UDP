#!/usr/bin/env python3
"""Phase 1 SDN controller: install shortest-path forwarding flows."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

import routing
import flows


class ControllerD1(app_manager.RyuApp):
    """Basic SDN controller using the routing and flow helpers."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ControllerD1, self).__init__(*args, **kwargs)
        self.datapaths = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        self.install_all_flows()

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def state_change_handler(self, ev):
        datapath = ev.datapath

        if ev.state == MAIN_DISPATCHER:
            self.datapaths[datapath.id] = datapath
            self.install_all_flows()
        elif ev.state == CONFIG_DISPATCHER:
            self.datapaths.pop(datapath.id, None)

    def install_all_flows(self):
        table = routing.next_hops()

        for datapath in self.datapaths.values():
            flows.install_flows(datapath, table)
