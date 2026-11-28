"""Fit the paired endpoints using train rows; select checkpoints on validation only."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

import torch

from .data import load_dataset, report_inputs
from .formats import NAMES, WIDTH, WEIGHT, normalized
from .learned import Autoencoder, file_digest


def examples(rows, device):
    domains, values = [], []
    for sample in rows:
        reports = report_inputs(sample)
        for index, domain in enumerate(NAMES):
            domains.append(index)
            values.append(normalized(domain, reports[domain]))
    return (torch.tensor(domains, device=device), torch.tensor(values, device=device))


def fit(args):
    data, _, provenance = load_dataset(args.dataset, ("train", "validation"))
    args.output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(args.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.set_num_threads(1)
    model = Autoencoder(args.kind, args.base).to(args.device)
    trainable = {name: parameter for name, parameter in model.named_parameters() if parameter.requires_grad}
    optimizer = torch.optim.AdamW(trainable.values(), lr=args.lr)
    train_domains, train_values = examples(data["train"], args.device)
    valid_domains, valid_values = examples(data["validation"], args.device)
    weights = torch.tensor([list(row) + [0.0] * (WIDTH - len(row)) for row in WEIGHT], device=args.device)

    def reconstruction(ids, values, predicted):
        weighted = weights[ids]
        return ((predicted - values).square() * weighted).sum() / weighted.sum()

    best = float("inf")
    best_checkpoint = {}
    history = []
    first = {}
    for epoch in range(1, args.epochs + 1):
        model.train()
        order = torch.randperm(len(train_domains), device=args.device)
        for batch in order.split(args.batch_size):
            ids, target = train_domains[batch], train_values[batch]
            reconstruction_values, probabilities = model(ids, target)
            error = reconstruction(ids, target, reconstruction_values)
            balance = (probabilities.mean(dim=0) - 0.5).square().mean()
            optimizer.zero_grad(set_to_none=True)
            (error + 0.001 * balance).backward()
            torch.nn.utils.clip_grad_norm_(trainable.values(), 1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            valid_predictions, _ = model(valid_domains, valid_values)
            train_predictions, _ = model(train_domains, train_values)
            valid_loss = reconstruction(valid_domains, valid_values, valid_predictions).item()
            train_loss = reconstruction(train_domains, train_values, train_predictions).item()
        if not torch.isfinite(torch.tensor(valid_loss)):
            raise ValueError("Nonfinite validation loss")
        if valid_loss < best:
            best, best_epoch = valid_loss, epoch
            best_checkpoint = {name: p.detach().cpu().clone() for name, p in trainable.items()}
        row = dict(epoch=epoch, train_loss=train_loss, validation_loss=valid_loss)
        if not first:
            first = deepcopy(row)
        history.append(row)
        if epoch == 1 or epoch % 10 == 0 or epoch == args.epochs:
            print(json.dumps(row), flush=True)

    with torch.no_grad():
        for name, parameter in trainable.items():
            parameter.copy_(best_checkpoint[name])
    changed = {}
    if args.kind == "lora":
        for end in ("sender", "receiver"):
            # PEFT initializes every lora_B matrix to zero.
            changed[end] = sum(p.detach().float().norm().item() ** 2
                               for name, p in trainable.items() if name.startswith(end) and "lora_B" in name) ** 0.5
            if changed[end] <= 0:
                raise ValueError(f"The {end} LoRA adapter did not train")
    model.save_endpoints(args.output)
    meta = {
        **provenance, "kind": args.kind,
        "train_ids": [row["record_id"] for row in data["train"]],
        "validation_ids": [row["record_id"] for row in data["validation"]],
        "seed": args.seed, "epochs": args.epochs, "batch_size": args.batch_size,
        "learning_rate": args.lr, "torch": str(torch.__version__),
        "device": torch.cuda.get_device_name(args.device) if args.device.startswith("cuda") else args.device,
        "best_epoch": best_epoch, "first_epoch": first, "best_validation_loss": best,
        "trainable_parameters": sum(p.numel() for p in trainable.values()),
        "total_parameters": sum(p.numel() for p in model.parameters()),
        "lora_b_norm": changed,
    }
    if args.base:
        meta["base_path"] = str(args.base.resolve())
        meta["base_sha256"] = {file: file_digest(args.base / file)
                               for file in ("model.safetensors", "config.json")}
        meta["pretrained_text_encoder"] = "openai/clip-vit-large-patch14 via FLUX.1-dev/text_encoder"
        import peft
        import transformers
        meta.update(peft=peft.__version__, transformers=transformers.__version__)
    (args.output / "fit.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (args.output / "history.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("mlp", "lora"))
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--seed", type=int, default=107)
    parser.add_argument("--lr", type=float, default=0.0003)
    args = parser.parse_args()
    if (args.kind == "lora") != (args.base is not None):
        parser.error("Provide the local CLIP text model directory for LoRA")
    if args.epochs <= 0 or args.batch_size <= 0 or args.lr <= 0:
        parser.error("Expected positive epochs, batch size and learning rate")
    fit(args)


if __name__ == "__main__":
    main()
