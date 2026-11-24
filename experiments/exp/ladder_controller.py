#!/usr/bin/env python3
"""Run a standalone closed-loop controller for the ladder simulation."""

import argparse
import importlib
import json
import socket
from pathlib import Path


VERSION = 1
MAX_MESSAGE_BYTES = 16384


class BacklogPolicy:
    """Throttle competing traffic while either measured queue is congested."""

    def __init__(self):
        self.healthy_samples = 0

    def __call__(self, observation):
        radio_bytes = observation["ran"]["dl_mac_virtual_buffer_bytes"]
        transport_packets = observation["transport"]["background_queue_packets"]
        core = observation["core"]
        active_rate = core["rate_bps"]

        if radio_bytes >= 8000 or transport_packets >= 8:
            self.healthy_samples = 0
            if active_rate != 2_000_000:
                return self.set_rate(core["flow_id"], 2_000_000)
        elif radio_bytes <= 2000 and transport_packets <= 1:
            self.healthy_samples += 1
            if self.healthy_samples >= 5 and active_rate != 20_000_000:
                return self.set_rate(core["flow_id"], 20_000_000)
        else:
            self.healthy_samples = 0
        return None

    @staticmethod
    def set_rate(flow_id, rate_bps):
        return {"type": "set_upf_rate", "flow_id": flow_id, "rate_bps": rate_bps}


def read_message(stream):
    line = stream.readline(MAX_MESSAGE_BYTES + 2)
    if not line:
        return None
    if len(line) > MAX_MESSAGE_BYTES + 1 or not line.endswith(b"\n"):
        raise ValueError("Incomplete or oversized simulator message")
    message = json.loads(line)
    if not isinstance(message, dict) or message.get("version") != VERSION:
        raise ValueError("Unexpected simulator protocol version")
    return message


def serve(listener, policy):
    listener.settimeout(10)
    connection, _ = listener.accept()
    with connection, connection.makefile("rwb") as stream:
        connection.settimeout(10)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        last_request = 0
        while (observation := read_message(stream)) is not None:
            request = observation["request_id"]
            if observation["type"] != "observation" or request != last_request + 1:
                raise ValueError(f"Unexpected observation for request {request}")
            decision = {
                "version": VERSION,
                "type": "decision",
                "request_id": request,
                "base_generation": observation["generation"],
                "action": policy(observation),
            }
            line = json.dumps(decision, allow_nan=False).encode("utf-8")
            if len(line) > MAX_MESSAGE_BYTES:
                raise ValueError("Oversized algorithm decision")
            stream.write(line + b"\n")
            stream.flush()
            ack = read_message(stream)
            if ack is None or ack["type"] != "ack" or ack["request_id"] != request:
                raise ValueError(f"Missing acknowledgement for request {request}")
            if ack["status"] not in ("noop", "unchanged"):
                print(json.dumps(ack), flush=True)
            last_request = request
        if last_request == 0:
            raise ValueError("Simulator disconnected without publishing an observation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="localhost port, 0 to auto-assign")
    parser.add_argument("--port-file", type=Path, help="write the bound port here when ready")
    parser.add_argument("--policy", help="optional Python module:function accepting an observation")
    args = parser.parse_args()
    policy = BacklogPolicy()
    if args.policy:
        module, separator, name = args.policy.partition(":")
        if not separator or not module or not name:
            parser.error("--policy must be module:function")
        policy = getattr(importlib.import_module(module), name)
        if not callable(policy):
            parser.error("--policy does not refer to a callable")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", args.port))
        listener.listen(1)
        port = listener.getsockname()[1]
        if args.port_file is not None:
            args.port_file.write_text(f"{port}\n", encoding="ascii")
        print(f"Listening on 127.0.0.1:{port}", flush=True)
        serve(listener, policy)


if __name__ == "__main__":
    main()
