"""Application-level reporting frames and independent per-domain triggers."""

from dataclasses import dataclass
import struct
from typing import Mapping, Protocol


@dataclass(frozen=True)
class Field:
    name: str
    full_format: str
    fixed_format: str
    step: int = 1
    categories: tuple[str, ...] = ()


SCHEMA = {
    "ran": (
        Field("ran_bands", "I", "B"),
        Field("ran_last_allocated_blocks", "I", "B"),
    ),
    "transport": (
        Field("path_id", "B", "B", categories=("direct", "detour")),
        Field("direct_queue_packets", "I", "B", step=8),
        Field("detour_queue_packets", "I", "B", step=8),
    ),
    "core": (Field("upf_video_rate_bps", "I", "H", step=100_000),),
}
DOMAIN_IDS = {name: index for index, name in enumerate(SCHEMA, start=1)}
FRAME_VERSION = 1
HEADER = struct.Struct("!BBBBQ")  # Protocol, codec ID, codec version, domain ID, source ns.
State = dict[str, int | str]


class Encoder(Protocol):
    def encode(self, domain: str, state: Mapping[str, int | str]) -> bytes: ...


class Decoder(Protocol):
    def decode(self, domain: str, payload: bytes) -> State: ...


@dataclass(frozen=True)
class Codec:
    codec_id: int
    version: int
    encoder: Encoder
    decoder: Decoder


def validate_state(domain: str, state: Mapping[str, int | str]) -> None:
    fields = SCHEMA[domain]
    if set(state) != {field.name for field in fields}:
        raise ValueError(f"Wrong fields for {domain}: {sorted(state)}")
    for field in fields:
        value = state[field.name]
        if field.categories:
            if value not in field.categories:
                raise ValueError(f"Invalid {field.name}: {value!r}")
        elif type(value) is not int or not 0 <= value < 2**32:
            raise ValueError(f"Expected uint32 for {field.name}, got {value!r}")


@dataclass(frozen=True)
class StructPayload:
    fixed_point: bool

    def layout(self, fields: tuple[Field, ...]) -> str:
        return "!" + "".join(
            field.fixed_format if self.fixed_point else field.full_format
            for field in fields
        )

    def encode(self, domain: str, state: Mapping[str, int | str]) -> bytes:
        validate_state(domain, state)
        fields = SCHEMA[domain]
        values = []
        for field in fields:
            value = state[field.name]
            if field.categories:
                value = field.categories.index(value)
            elif self.fixed_point:
                value = (value + field.step // 2) // field.step
            values.append(value)
        try:
            return struct.pack(self.layout(fields), *values)
        except struct.error as error:
            raise ValueError(f"{domain} payload exceeds codec range: {state}") from error

    def decode(self, domain: str, payload: bytes) -> State:
        fields = SCHEMA[domain]
        try:
            values = struct.unpack(self.layout(fields), payload)
            state = {}
            for field, value in zip(fields, values):
                if field.categories:
                    state[field.name] = field.categories[value]
                else:
                    state[field.name] = value * field.step if self.fixed_point else value
        except (struct.error, IndexError) as error:
            raise ValueError(f"Invalid {domain} payload") from error
        validate_state(domain, state)
        return state


full_payload = StructPayload(fixed_point=False)
fixed_payload = StructPayload(fixed_point=True)
FULL = Codec(1, 1, full_payload, full_payload)
FIXED = Codec(2, 1, fixed_payload, fixed_payload)


def frame(codec: Codec, domain: str, source_ns: int, state: State) -> bytes:
    return (
        HEADER.pack(FRAME_VERSION, codec.codec_id, codec.version, DOMAIN_IDS[domain], source_ns)
        + codec.encoder.encode(domain, state)
    )


def unframe(codec: Codec, domain: str, wire: bytes) -> tuple[int, State]:
    if len(wire) < HEADER.size:
        raise ValueError("Truncated report header")
    version, codec_id, codec_version, domain_id, source_ns = HEADER.unpack_from(wire)
    if (version, codec_id, codec_version, domain_id) != (
        FRAME_VERSION, codec.codec_id, codec.version, DOMAIN_IDS[domain]
    ):
        raise ValueError("Report header does not match the configured protocol, codec or domain")
    state = codec.decoder.decode(domain, wire[HEADER.size:])
    validate_state(domain, state)
    return source_ns, state


class Trigger(Protocol):
    def reason(
        self, domain: str, now_ns: int, current: State, previous: tuple[int, State] | None
    ) -> str | None: ...


class Periodic:
    def reason(self, domain, now_ns, current, previous):
        return "periodic"


@dataclass(frozen=True)
class Threshold:
    max_silence_ns: int
    thresholds: Mapping[str, int]

    def __post_init__(self):
        expected = {
            field.name for fields in SCHEMA.values() for field in fields if not field.categories
        }
        if set(self.thresholds) != expected or any(
            type(value) is not int or value <= 0 for value in self.thresholds.values()
        ):
            raise ValueError("Provide a positive integer threshold for every numeric field")
        if type(self.max_silence_ns) is not int or self.max_silence_ns <= 0:
            raise ValueError("Maximum silence must be a positive integer in ns")

    def reason(self, domain, now_ns, current, previous):
        if previous is None:
            return "initial"
        last_ns, last = previous
        for field in SCHEMA[domain]:
            value, old = current[field.name], last[field.name]
            if field.categories:
                changed = value != old
            else:
                changed = abs(value - old) >= self.thresholds[field.name]
            if changed:
                return "threshold"
        if now_ns - last_ns >= self.max_silence_ns:
            return "max_silence"
        return None
