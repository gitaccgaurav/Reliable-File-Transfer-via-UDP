import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdn"))
import routing
from net_config import link_id

class RoutingTests(unittest.TestCase):
	
	def test_primary_path_when_healthy(self):
		self.assertEqual(routing.path("h1", "h2"), [1, 2, 4])
		self.assertEqual(routing.path("h2", "h1"), [4, 2, 1])
		
	def test_primary_link_down_uses_backup(self):
		self.assertEqual(routing.path("h1", "h2", {link_id(1, 2)}), [1, 3, 4])
		self.assertEqual(routing.path("h1", "h2", {link_id(2, 4)}), [1, 3, 4])
		
	def test_recovery_returns_to_primary(self):
		self.assertEqual(routing.path("h1", "h2", set()), [1, 2, 4])
		
	def test_both_paths_down_is_unreachable(self):
		self.assertIsNone(routing.path("h1", "h2", {link_id(1, 2), link_id(1, 3)}))
	
	def test_ports_for_h2(self):
		hops = routing.next_hops()["h2"]
		self.assertEqual(hops[4], 3) # s4 -> h2
		self.assertEqual(hops[2], 2) # s2 -> s4
		self.assertEqual(hops[1], 2) # s1 -> s2
		self.assertEqual(routing.next_hops({link_id(1, 2)})["h2"][1], 3) # s1 -> s3
		
	def test_same_switch_hosts(self):
		self.assertEqual(routing.path("h1", "h3"), [1])
		
	def test_link_of(self):
		self.assertEqual(routing.link_of(1, 2), link_id(1, 2))
		self.assertEqual(routing.link_of(2, 1), link_id(1, 2))
		self.assertIsNone(routing.link_of(1, 1)) # host port
		
if __name__ == "__main__":
	unittest.main()