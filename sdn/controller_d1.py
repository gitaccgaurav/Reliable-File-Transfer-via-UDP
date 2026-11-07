"""D1 controller: proactively install forwarding rules for the PRIMARY path only.

Run: ryu-manager sdn/controller_d1.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

import routing
from flows import install_flows


class StaticPathController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch_features(self, ev):
        dp = ev.msg.datapath
        self.logger.info("switch s%d connected -> installing flows", dp.id)
        install_flows(dp, routing.next_hops())  # no links down yet
        self.logger.info(
            "active route h1->h2: %s",
            routing.path_str(routing.path("h1", "h2"))
        )
