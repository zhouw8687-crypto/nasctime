"""Encode the local summaries used by the ladder controller experiment."""

import socket
import struct
from dataclasses import dataclass

import numpy as np


DOMAINS = ("core", "transport", "ran")
PAYLOADS = (struct.Struct("!5H"), struct.Struct("!5B"), struct.Struct("!3IBH"))
HEADER = struct.Struct("!BBH")  # protocol version, domain, observation id
VERSION = 1
SCALES = np.array([
    [48, 48, 48, 36, 48],
    [96, 96, 96, 8, 100],
    [45000, 45000, 45000, 6, 450],
], dtype=float)


def features(case, observations):
    """Treat port bitrate and the UE location as local configuration context."""
    history = [observations[max(0, len(observations) - back)] for back in (1, 2, 3, 4)]
    core = [row["core"] for row in history]
    transport = [row["transport"] for row in history]
    ran = [row["ran"] for row in history]
    offered = [row["admitted_packets"] + row["dropped_packets"] for row in core]
    increments = [new - old for new, old in zip(offered, offered[1:])]
    return (
        (*increments, core[0]["dropped_packets"] - core[1]["dropped_packets"],
         core[0]["admitted_packets"] - core[1]["admitted_packets"]),
        tuple(row["background_queue_packets"] for row in transport[:3])
        + (transport[0]["priority_queue_packets"], case["link_mbps"]),
        tuple(row["dl_mac_virtual_buffer_bytes"] for row in ran[:3])
        + (ran[0]["dl_last_slot_allocated_blocks"], case["ue_x_m"]),
    )


def scale(state):
    return np.asarray(state, dtype=float) / SCALES


@dataclass
class ManualCodec:
    domain: int

    def encode(self, vector):
        # Two four-bit fields. Use recent offered load, queue depth and configured capacity.
        if self.domain == 0:
            values = (max(vector[:2]), vector[1])
            levels = (48, 48)
        elif self.domain == 1:
            values = (max(vector[:3]), vector[4])
            levels = (128, 100)
        else:
            values = (max(vector[:3]), vector[4])
            levels = (55000, 450)
        a, b = (min(15, round(value * 15 / limit)) for value, limit in zip(values, levels, strict=True))
        return bytes([(a << 4) | b])

    def decode(self, payload):
        value, = payload
        a, b = value >> 4, value & 15
        if self.domain == 0:
            now, previous = round(a * 48 / 15), round(b * 48 / 15)
            return (now, previous, previous, 0, now)
        if self.domain == 1:
            queue = round(a * 128 / 15)
            return (queue, queue, queue, 0, round(b * 100 / 15))
        buffer = round(a * 55000 / 15)
        return (buffer, buffer, buffer, 4, round(b * 450 / 15))


class LearnedCodec:
    """A per-domain codebook trained on telemetry with decision-relevance weights."""

    def __init__(self, domain, histories, labels, codewords=16):
        self.domain = domain
        points = histories[:, :, domain, :] / SCALES[domain]
        final = points[:, -1]
        final_centered = final - final.mean(axis=0)
        targets = labels - labels.mean(axis=0)
        covariance = final_centered.T @ targets
        norm = np.linalg.norm(final_centered, axis=0)[:, None] * np.linalg.norm(targets, axis=0)[None, :]
        relevance = np.divide(covariance, norm, out=np.zeros_like(covariance), where=norm > 0)
        self.weights = .25 + np.mean(abs(relevance), axis=1)
        training = points.reshape(-1, final.shape[-1])
        # Include past states, but give the state used for the control decision more weight.
        training = np.concatenate((training, final, final))
        self.centers = self.fit(training, codewords)

    def distances(self, inputs, centers):
        return np.sum((inputs[:, None, :] - centers[None, :, :]) ** 2 * self.weights, axis=-1)

    def fit(self, points, codewords):
        # Deterministic farthest-first initialization followed by Lloyd updates.
        centers = points[[0]]
        for _ in range(1, codewords):
            nearest = self.distances(points, centers).min(axis=1)
            if nearest.max() < 1e-15:
                break
            centers = np.concatenate((centers, points[[int(nearest.argmax())]]))
        for _ in range(40):
            assignment = self.distances(points, centers).argmin(axis=1)
            updated = np.array([
                points[assignment == index].mean(axis=0) if np.any(assignment == index) else center
                for index, center in enumerate(centers)
            ])
            if np.allclose(centers, updated, rtol=0, atol=1e-10):
                break
            centers = updated
        return centers

    def encode(self, vector):
        value = np.array([vector], dtype=float) / SCALES[self.domain]
        return bytes([int(self.distances(value, self.centers).argmin())])

    def decode(self, payload):
        index, = payload
        return self.centers[index] * SCALES[self.domain]


class LocalReports:
    """Exchange application frames over a local socket and retain the last decoded state."""

    def __init__(self, mode, encoder, decoder):
        self.mode = mode
        self.encoder = encoder
        self.decoder = decoder
        self.sample_ids = np.zeros(len(DOMAINS), dtype=int)
        self.previous = [None] * len(DOMAINS)
        self.decoded = [None] * len(DOMAINS)
        self.bits = 0
        self.frames = 0

    def exchange(self, sender, receiver, observation_id, state):
        for domain, vector in enumerate(state):
            if self.mode == "threshold" and self.previous[domain] is not None:
                elapsed = observation_id - self.sample_ids[domain]
                movement = abs(np.array(vector) - self.previous[domain]) / SCALES[domain]
                if elapsed < 3 and movement.max() < .20:
                    continue
            message = HEADER.pack(VERSION, domain, observation_id) + self.encoder(domain, vector)
            sender.sendall(message)
            received = receiver.recv(len(message), socket.MSG_WAITALL)
            version, owner, sample_id = HEADER.unpack_from(received)
            if len(received) != len(message) or (version, owner, sample_id) != (VERSION, domain, observation_id):
                raise ValueError("Invalid local report received")
            self.bits += len(received) * 8
            self.frames += 1
            self.decoded[domain] = self.decoder(domain, received[HEADER.size:])
            self.previous[domain] = np.array(vector)
            self.sample_ids[domain] = observation_id

    @property
    def state(self):
        return np.array(self.decoded, dtype=float)


def reporter(mode, learned):
    if mode in ("full", "threshold"):
        return LocalReports(mode, lambda domain, value: PAYLOADS[domain].pack(*value),
                            lambda domain, data: PAYLOADS[domain].unpack(data))
    codecs = [ManualCodec(domain) for domain in range(len(DOMAINS))] if mode == "manual" else learned
    return LocalReports(mode, lambda domain, value: codecs[domain].encode(value),
                        lambda domain, data: codecs[domain].decode(data))
