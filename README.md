# Reliable-File-Transfer-via-UDP
Reliable file transfer over UDP (Stop-and-Wait and Selective Repeat) running on an SDN built with Mininet and a Ryu controller, with automatic rerouting on link failure.
## Agreed interfaces
- Packet format: frozen in protocol.py. Nobody changes it without telling all.
- Sender flags: FILE HOST [--port --name --drop-rate --no-notify --stats-file -v]
- Receiver flags: [--bind --port --out-dir --drop-ack -v]
- Sender output contract: the LAST line the sender prints is one JSON object.
- Network layout: only sdn/net_config.py defines IPs, ports and links.
- Logs: logs/controller_events.csv, logs/port_stats.csv, logs/receiver_summary.jsonl
