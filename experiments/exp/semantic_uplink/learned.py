"""Jointly train independent PEFT encoder/decoder endpoints through 32 hard bits."""

from hashlib import sha256
import json
import os
from pathlib import Path

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

from integrated_review.uplink import Codec
from .formats import NAMES, PAYLOAD_BYTES, WIDTH, normalized, restored


BITS = 8 * PAYLOAD_BYTES
ADAPTER_TARGETS = ["q_proj", "v_proj"]


def file_digest(path):
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MlpEnd(nn.Module):
    def __init__(self, size, output):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(size + len(NAMES), 48), nn.GELU(),
                                 nn.Linear(48, 48), nn.GELU(), nn.Linear(48, output))

    def forward(self, domains, values):
        domain_one_hot = F.one_hot(domains, num_classes=len(NAMES))
        return self.net(torch.cat((domain_one_hot, values.flatten(1)), dim=1))


class ClipLoraEnd(nn.Module):
    def __init__(self, base_dir, input_width, output, adapter_dir=None):
        super().__init__()
        from peft import LoraConfig, PeftModel, get_peft_model
        from transformers import CLIPTextModel

        base = CLIPTextModel.from_pretrained(base_dir, local_files_only=True, dtype=torch.float32)
        if adapter_dir is None:
            self.backbone = get_peft_model(base, LoraConfig(
                r=8, lora_alpha=16, target_modules=ADAPTER_TARGETS, bias="none",
            ))
        else:
            self.backbone = PeftModel.from_pretrained(base, adapter_dir)
        hidden = base.config.hidden_size
        self.projection = nn.Linear(input_width, hidden)
        self.domains = nn.Embedding(len(NAMES), hidden)
        self.head = nn.Sequential(nn.LayerNorm(hidden), nn.Linear(hidden, output))

    def forward(self, domains, values):
        clip = self.backbone.get_base_model().text_model
        sequence = torch.cat((self.domains(domains)[:, None], self.projection(values)), dim=1)
        length = sequence.size(1)
        position = clip.embeddings.position_embedding(torch.arange(length, device=sequence.device))
        mask = sequence.new_full((length, length), torch.finfo(sequence.dtype).min).triu(1)
        encoded = clip.encoder(
            inputs_embeds=sequence + position,
            causal_attention_mask=mask[None, None].expand(len(sequence), 1, length, length),
        ).last_hidden_state
        return self.head(clip.final_layer_norm(encoded[:, -1]))

    def save_end(self, folder):
        self.backbone.save_pretrained(folder)
        torch.save({
            name: module.state_dict() for name, module in
            (("projection", self.projection), ("domains", self.domains), ("head", self.head))
        }, folder / "report_heads.pt")

    def load_heads(self, folder):
        state = torch.load(folder / "report_heads.pt", map_location="cpu", weights_only=True)
        for name, values in state.items():
            getattr(self, name).load_state_dict(values)


class Autoencoder(nn.Module):
    def __init__(self, kind, base=None, artifact=None):
        super().__init__()
        self.kind = kind
        if kind == "lora":
            self.sender = ClipLoraEnd(base, 1, BITS, artifact / "sender" if artifact else None)
            self.receiver = ClipLoraEnd(base, 8, WIDTH, artifact / "receiver" if artifact else None)
            if artifact:
                self.sender.load_heads(artifact / "sender")
                self.receiver.load_heads(artifact / "receiver")
        elif kind == "mlp":
            self.sender = MlpEnd(WIDTH, BITS)
            self.receiver = MlpEnd(BITS, WIDTH)
            if artifact:
                state = torch.load(artifact / "model.pt", map_location="cpu", weights_only=True)
                self.load_state_dict(state)
        else:
            raise ValueError(f"Unknown learned codec {kind}")

    def probabilities(self, domains, values):
        inputs = values.unsqueeze(-1) if self.kind == "lora" else values
        return torch.sigmoid(self.sender(domains, inputs))

    def reconstruct(self, domains, bits):
        inputs = bits.reshape(len(bits), PAYLOAD_BYTES, 8) if self.kind == "lora" else bits
        return torch.sigmoid(self.receiver(domains, inputs))

    def forward(self, domains, values):
        soft = self.probabilities(domains, values)
        hard = (soft >= 0.5).to(soft.dtype)
        wire_bits = soft + (hard - soft).detach()
        return self.reconstruct(domains, wire_bits), soft

    def save_endpoints(self, folder):
        if self.kind == "lora":
            self.sender.save_end(folder / "sender")
            self.receiver.save_end(folder / "receiver")
        else:
            torch.save(self.state_dict(), folder / "model.pt")


class LearnedSender:
    def __init__(self, endpoint, kind, device):
        self.endpoint = endpoint
        self.kind = kind
        self.device = device

    @torch.inference_mode()
    def encode(self, domain, report):
        domains = torch.tensor([NAMES.index(domain)], device=self.device)
        values = torch.tensor([normalized(domain, report)], device=self.device)
        inputs = values.unsqueeze(-1) if self.kind == "lora" else values
        bits = (self.endpoint(domains, inputs)[0] >= 0).cpu().numpy()
        return np.packbits(bits, bitorder="big").tobytes()


class LearnedReceiver:
    def __init__(self, endpoint, kind, device):
        self.endpoint = endpoint
        self.kind = kind
        self.device = device

    @torch.inference_mode()
    def decode(self, domain, payload):
        if len(payload) != PAYLOAD_BYTES:
            raise ValueError(f"Expected exactly {PAYLOAD_BYTES} bytes")
        domains = torch.tensor([NAMES.index(domain)], device=self.device)
        bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8), bitorder="big")
        wire = torch.as_tensor(bits, dtype=torch.float32, device=self.device).unsqueeze(0)
        inputs = wire.reshape(1, PAYLOAD_BYTES, 8) if self.kind == "lora" else wire
        features = torch.sigmoid(self.endpoint(domains, inputs)[0]).cpu().tolist()
        return restored(domain, features)


def load_learned(folder, device):
    meta = json.loads((folder / "fit.json").read_text(encoding="utf-8"))
    base = None
    if meta["kind"] == "lora":
        base = Path(os.environ.get("SEMANTIC_BASE_MODEL", meta["base_path"]))
        for file, digest in meta["base_sha256"].items():
            if file_digest(base / file) != digest:
                raise ValueError(f"Base checkpoint digest changed for {file}")
    model = Autoencoder(meta["kind"], base, folder).to(device).eval()
    codec_id = 23 if meta["kind"] == "mlp" else 24
    return Codec(codec_id, 1, LearnedSender(model.sender, model.kind, device),
                 LearnedReceiver(model.receiver, model.kind, device))


def make_learned():
    torch.set_num_threads(1)
    device = os.environ.get("SEMANTIC_DEVICE", "cuda")
    return load_learned(Path(os.environ["SEMANTIC_CODEC_DIR"]), device)
