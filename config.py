"""Shared settings. Sender, receiver and scripts all import this file."""
PORT = 5005 # UDP port the receiver listens on
CHUNK_SIZE = 1000 # file bytes carried by one DATA packet
RECV_DIR = "received_files" # where the receiver writes finished files
LOG_DIR = "logs"
# --- Stop-and-wait (D1) ---
TIMEOUT = 0.5 
MAX_RETRIES = 15 # seconds to wait for an ACK before resending
# resends of ONE packet before giving up
# --- Selective Repeat (D2) ---
WINDOW_SIZE = 16 
RTO_INIT = 0.5 
RTO_MIN = 0.2
RTO_MAX = 2.0
# packets allowed in flight at once
# starting retransmission timeout (seconds)
# --- Application -> SDN controller notification (D2) ---
NOTIFY_SOCK = "/tmp/sdn_notify.sock" # Unix datagram socket the controller owns
NOTIFY_AFTER = 5 # consecutive timeouts before telling the controller