import socket
import json

from config import NOTIFY_SOCK, NOTIFY_AFTER


def notify_controller(tid, seq, retries):
    if retries < NOTIFY_AFTER:
        return False

    message = {
        "tid": tid,
        "seq": seq,
        "retries": retries
    }

    client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

    try:
        client.sendto(
            json.dumps(message).encode(),
            NOTIFY_SOCK
        )
        return True

    except OSError:
        return False

    finally:
        client.close()
