"""Application -> SDN controller channel."""

import json
import socket
import config


def notify_controller(event, **info):
    """Fire-and-forget. Returns False if no controller is listening."""
    msg = json.dumps({"event": event, **info}).encode()

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.sendto(msg, config.NOTIFY_SOCK)
        s.close()
        return True
    except OSError:
        return False
