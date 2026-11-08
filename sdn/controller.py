"""D2 controller: monitors links, reroutes on failure, recovers, listens to the app.

Run: ryu-manager sdn/controller.py
Static baseline: REROUTE=0 ryu-manager sdn/controller.py
"""
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE)) # repo root, for config.py

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3

import config
import routing
from flows import install_flows
from net_config import HOSTS, link_id

REROUTE = os.environ.get("REROUTE", "1") != "0"		# REROUTE=0 -> baseline that never reroutes
STATS_INTERVAL = 2.0 								# seconds between port-stats polls
SUSPECT_SECONDS = 15.0 								# how long an app-blamed link stays avoided
APP_COOLDOWN = 5.0 									# min seconds between app-triggered reroute

class RerouteController(app_manager.RyuApp):
	OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.datapaths = {}		 	# dpid -> datapath
		self.down_ports = set()		# (dpid, port_no) currently reporting link-down
		self.suspect = {} 			# link_id -> expiry time (blamed by an app report
		self.last_app_reroute = 0.0
		self.prev_stats = {}
		os.makedirs(config.LOG_DIR, exist_ok=True)
		self.events = self._open_csv("controller_events.csv", "time,event,detail")
		self.stats_csv = self._open_csv(
				"port_stats.csv", "time,dpid,port,rx_pkts,tx_pkts,rx_bytes,tx_bytes,tx_kbps")
		self.log_event("controller_start", f"reroute={'on' if REROUTE else 'off'}")
		hub.spawn(self._stats_loop)
		hub.spawn(self._notify_loop)
		
		# ---------- small helpers ----------
	def _open_csv(self, name, header):
		path = os.path.join(config.LOG_DIR, name)
		new = not os.path.exists(path) or os.path.getsize(path) == 0
		f = open(path, "a", buffering=1)
		if new:
			f.write(header + "\n")
		return f
		
		
	def log_event(self, event, detail=""):
		self.events.write(f"{time.time():.3f},{event},{detail}\n")
		self.logger.info("%s %s", event.upper(), detail)


	def active_down_links(self):
		if not REROUTE:
			return set()
		now = time.time()
		links = {routing.link_of(d, p) for d, p in self.down_ports}
		links |= {l for l, expiry in self.suspect.items() if expiry > now}
		links.discard(None)
		return links

	def recompute(self, reason):
		down = self.active_down_links()
		table = routing.next_hops(down)
		for dp in self.datapaths.values():
			install_flows(dp, table)
		route = routing.path_str(routing.path("h1", "h2", down))
		self.log_event("reroute", f"{reason}; h1->h2 now {route}")
		
	# ---------- OpenFlow events ----------
	@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
	def on_switch_features(self, ev):
		dp = ev.msg.datapath
		self.datapaths[dp.id] = dp
		install_flows(dp, routing.next_hops(self.active_down_links()))		
		self.log_event("switch_connected", f"s{dp.id}")
		
	@set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
	def on_port_status(self, ev):
		msg, dp = ev.msg, ev.msg.datapath
		ofp, desc = dp.ofproto, ev.msg.desc
		link = routing.link_of(dp.id, desc.port_no)
		if link is None: # host-facing port: not our concern
			return		
		is_down = bool(desc.state & ofp.OFPPS_LINK_DOWN or desc.config & ofp.OFPPC_PORT_DOWN
						or msg.reason == ofp.OFPPR_DELETE)
		key = (dp.id, desc.port_no)
		if is_down == (key in self.down_ports):
			return # no change
		(self.down_ports.add if is_down else self.down_ports.discard)(key)
		a, b = sorted(link)
		self.log_event("link_down" if is_down else "link_up",
						f"s{a}-s{b} (seen at s{dp.id} port {desc.port_no})")
		if REROUTE:
			self.recompute("link " + ("failure" if is_down else "recovery"))
			
	@set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
	def on_port_stats(self, ev):
		dpid, now = ev.msg.datapath.id, time.time()
		for st in ev.msg.body:
			if st.port_no >= 0xFFFFFF00: # skip the LOCAL port
				continue
			prev = self.prev_stats.get((dpid, st.port_no))
			kbps = (st.tx_bytes - prev[1]) * 8 / 1000 / max(now - prev[0], 1e-6) if prev else 0.0
			self.prev_stats[(dpid, st.port_no)] = (now, st.tx_bytes)
			self.stats_csv.write(f"{now:.3f},{dpid},{st.port_no},{st.rx_packets},{st.tx_packets},"
								f"{st.rx_bytes},{st.tx_bytes},{kbps:.1f}\n")
	# ---------- background loops ----------
	def _stats_loop(self):
		while True:
			for dp in list(self.datapaths.values()):
				dp.send_msg(dp.ofproto_parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))
			self._expire_suspects()
			hub.sleep(STATS_INTERVAL)

	def _expire_suspects(self):
		now = time.time()
		gone = [l for l, expiry in self.suspect.items() if expiry <= now]
		for l in gone:
			del self.suspect[l]
		if gone and REROUTE:
			self.recompute("suspect link timeout, trying primary again")

	def _notify_loop(self):
		"""Receive 'path_problem' reports sent by the file-transfer app."""
		path = config.NOTIFY_SOCK
		if os.path.exists(path):
			os.unlink(path)
		sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
		sock.bind(path)
		os.chmod(path, 0o666)
		while True:
			try:
				msg = json.loads(sock.recv(4096))
			except ValueError:
				continue
			if msg.get("event") == "path_problem":
				self.on_path_problem(msg)

	def on_path_problem(self, msg):
		self.log_event("app_report", json.dumps(msg).replace(",", ";"))
		now = time.time()
		src = msg.get("src")
		dst = next((h for h, v in HOSTS.items() if v[0] == msg.get("dst_ip")), None)
		if not REROUTE or src not in HOSTS or dst is None:
			return
		if now - self.last_app_reroute < APP_COOLDOWN:
			return
		down = self.active_down_links()
		route = routing.path(src, dst, down)
		if not route or len(route) < 2:
			return
		# Heuristic: the app cannot say WHICH link is bad, so blame the first
		# core link of the route in use and see whether the alternate works.
		blamed = link_id(route[0], route[1])
		if routing.path(src, dst, down | {blamed}) is None:
			return # no alternative: do not cut ourselves off
		self.suspect[blamed] = now + SUSPECT_SECONDS
		self.last_app_reroute = now
		a, b = sorted(blamed)
		self.recompute(f"app reported timeouts, avoiding s{a}-s{b}")
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		