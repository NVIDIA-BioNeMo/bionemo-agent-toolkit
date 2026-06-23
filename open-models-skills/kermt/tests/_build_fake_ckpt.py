#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Test utility: build a fake grover_base (vocab-only) checkpoint whose vocab
heads match a given pair of atom + bond vocab files.

Produces a save format identical to task/kermttrainer.py's `save_checkpoint`
so pretrain_ddp.py's `trainer.load` can pick it up via the auto-resume path
(`<save_dir>/last_checkpoint.pt`).

Run inside the kermt container — needs the kermt package + torch + the vocab
loader. Not invoked in production; lives under agent/tests/ because that's the
only context that needs to forge a checkpoint.

Usage
-----
    python agent/tests/_build_fake_ckpt.py \
        --atom-vocab tests/data/pretrain/pretrain_atom_vocab.json \
        --bond-vocab tests/data/pretrain/pretrain_bond_vocab.json \
        --out /tmp/fake_grover_base.pt \
        [--hidden-size 800] [--depth 6] [--num-attn-head 4]
"""
from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path

import torch

from kermt.data.torchvocab import MolVocab
from kermt.model.models import KermtTask, KERMTEmbedding


def make_args(*, hidden_size: int, depth: int, num_attn_head: int,
              epochs: int, warmup_epochs: float,
              init_lr: float, max_lr: float, final_lr: float) -> Namespace:
    """Mirror the args Namespace pretrain_ddp.py builds for a vocab-only run.
    Only the fields KermtTask / KERMTEmbedding actually read are populated,
    plus the schedule args the runner's --resume mode inherits via
    `ckpt.args.<field>`."""
    return Namespace(
        # Architecture
        hidden_size=hidden_size,
        depth=depth,
        num_attn_head=num_attn_head,
        num_mt_block=1,
        dropout=0.1,
        activation="PReLU",
        backbone="gtrans",
        embedding_output_type="both",
        bias=False,
        undirected=False,
        bond_drop_rate=0,
        dist_coff=0.1,
        # Self-attention readout (off by default for vocab-only pretrain)
        self_attention=False,
        attn_hidden=4,
        attn_out=8,
        # Misc
        cuda=False,
        input_layer="fc",
        dense=False,
        # Tokens to make it recognizable downstream
        pretrain_mode="vocab",
        # Schedule args — needed for --resume to inherit via ckpt.saved_args.
        # Defaults match a small fast-training profile (e.g., epochs=1,
        # warmup_epochs=0) when used by e2e tests.
        epochs=epochs,
        warmup_epochs=warmup_epochs,
        init_lr=init_lr,
        max_lr=max_lr,
        final_lr=final_lr,
    )


def build_checkpoint(*, atom_vocab_path: Path, bond_vocab_path: Path,
                     out_path: Path, hidden_size: int = 800, depth: int = 6,
                     num_attn_head: int = 4,
                     epochs: int = 1, warmup_epochs: float = 0.0,
                     init_lr: float = 1e-5, max_lr: float = 1e-4, final_lr: float = 1e-5,
                     scheduler_step: int = 0, batch_idx: int = 0, epoch: int = 0) -> dict:
    """Returns the saved state dict (already written to out_path)."""
    atom = MolVocab.load_vocab(str(atom_vocab_path))
    bond = MolVocab.load_vocab(str(bond_vocab_path))
    atom_size = len(atom)
    bond_size = len(bond)
    fg_size = 85  # KermtTask.__init__ default; matches FG-task head dimensions

    args = make_args(
        hidden_size=hidden_size, depth=depth, num_attn_head=num_attn_head,
        epochs=epochs, warmup_epochs=warmup_epochs,
        init_lr=init_lr, max_lr=max_lr, final_lr=final_lr,
    )

    # Build the same model pretrain_ddp.py would build for --pretrain_mode vocab
    kermt = KERMTEmbedding(args)
    model = KermtTask(args, kermt, atom_vocab_size=atom_size, bond_vocab_size=bond_size, fg_size=fg_size)

    # Optimizer + scheduler state_dicts match what save_checkpoint serializes.
    # NoamLR has its own internal state but save_checkpoint only persists
    # scheduler_step (an int), so we don't need a real scheduler here.
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-5, weight_decay=1e-7)

    state = {
        "args": args,
        "state_dict": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scheduler_step": scheduler_step,
        "batch_idx": batch_idx,
        "epoch": epoch,
        "data_scaler": None,
        "features_scaler": None,
        "wandb_run_id": None,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, out_path)
    return state


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--atom-vocab", required=True)
    p.add_argument("--bond-vocab", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--hidden-size", type=int, default=800)
    p.add_argument("--depth", type=int, default=6)
    p.add_argument("--num-attn-head", type=int, default=4)
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--warmup-epochs", type=float, default=0.0)
    p.add_argument("--init-lr", type=float, default=1e-5)
    p.add_argument("--max-lr", type=float, default=1e-4)
    p.add_argument("--final-lr", type=float, default=1e-5)
    p.add_argument("--scheduler-step", type=int, default=0,
                   help="Bake a nonzero scheduler_step into the ckpt (for testing "
                        "--resume's restore-from-mid-run path).")
    p.add_argument("--batch-idx", type=int, default=0,
                   help="Bake a nonzero batch_idx into the ckpt (for testing "
                        "--resume's mid-epoch sampler skip).")
    p.add_argument("--epoch", type=int, default=0)
    args = p.parse_args()
    state = build_checkpoint(
        atom_vocab_path=Path(args.atom_vocab),
        bond_vocab_path=Path(args.bond_vocab),
        out_path=Path(args.out),
        hidden_size=args.hidden_size, depth=args.depth, num_attn_head=args.num_attn_head,
        epochs=args.epochs, warmup_epochs=args.warmup_epochs,
        init_lr=args.init_lr, max_lr=args.max_lr, final_lr=args.final_lr,
        scheduler_step=args.scheduler_step, batch_idx=args.batch_idx, epoch=args.epoch,
    )
    print(f"Wrote {args.out}: {len(state['state_dict'])} state-dict tensors, "
          f"epoch={state['epoch']}, scheduler_step={state['scheduler_step']}, "
          f"batch_idx={state['batch_idx']}")


if __name__ == "__main__":
    main()
