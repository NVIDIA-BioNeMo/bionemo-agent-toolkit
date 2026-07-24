#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Drive the open Proteina-Complexa `complexa` CLI: build argv -> run -> discover -> extract.

Transport-agnostic and stdlib-only. Runs the upstream `complexa` Hydra CLI inside
your local checkout ($COMPLEXA_REPO) and reads the generated complex PDBs from
`./inference/`. Hotspots and binder length are target-dict-driven upstream, so
register the target first (`complexa target add ...`) and select it with --task-name.

Examples
  COMPLEXA_REPO=/path/to/Proteina-Complexa \
    python complexa_design.py run --task-name <task-name> --run-name <run> \
      --algorithm best-of-n --num-samples 8 --seed 0 --out outputs/<run>
  python complexa_design.py extract outputs/<run>/inference/**/complex_0.pdb

See references/complexa-cli.md for the full override list.
"""
from __future__ import annotations
import argparse, os, shutil, subprocess, sys, time
from pathlib import Path

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}
DEFAULT_CONFIG = "configs/search_binder_local_pipeline.yaml"


def repo_root() -> Path:
    r = os.environ.get("COMPLEXA_REPO")
    if not r:
        sys.exit("Set COMPLEXA_REPO to your Proteina-Complexa checkout "
                 "(https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa).")
    p = Path(r).expanduser()
    if not p.is_dir():
        sys.exit(f"COMPLEXA_REPO is not a directory: {p}")
    return p


def build_argv(a) -> list[str]:
    verb = "generate" if a.mode == "generate" else "design"
    argv = [a.cli_bin, verb, a.config, f"++run_name={a.run_name}"]
    if a.task_name:
        argv.append(f"++generation.task_name={a.task_name}")
    if a.algorithm:
        argv.append(f"++generation.search.algorithm={a.algorithm}")
    if a.num_samples is not None:
        argv.append(f"++generation.dataloader.dataset.nres.nsamples={a.num_samples}")
    if a.seed is not None:
        argv.append(f"++seed={a.seed}")
    if a.gen_njobs is not None:
        argv.append(f"++gen_njobs={a.gen_njobs}")
    if a.eval_njobs is not None:
        argv.append(f"++eval_njobs={a.eval_njobs}")
    if a.ckpt_path:
        argv.append(f"++ckpt_path={a.ckpt_path}")
    if a.ckpt_name:
        argv.append(f"++ckpt_name={a.ckpt_name}")
    if a.autoencoder_ckpt_path:
        argv.append(f"++autoencoder_ckpt_path={a.autoencoder_ckpt_path}")
    argv.extend(a.override or [])  # caller escape hatch, appended last so it wins
    return argv


def discover_complex_pdbs(root: Path, since: float | None = None) -> list[Path]:
    inf = root / "inference"
    if not inf.is_dir():
        return []
    pdbs = [p for p in inf.rglob("*.pdb") if p.is_file()]
    if since is not None:
        pdbs = [p for p in pdbs if p.stat().st_mtime >= since - 1]
    return sorted(pdbs)


def extract(pdb_path: str) -> dict:
    """Return {chain: sequence} from CA records (binder chain carries the seq)."""
    chains: dict[str, list[str]] = {}
    for line in Path(pdb_path).read_text().splitlines():
        if line[:6].strip() in ("ATOM", "HETATM") and line[12:16].strip() == "CA":
            ch = line[21]
            chains.setdefault(ch, []).append(THREE_TO_ONE.get(line[17:20].strip(), "X"))
    seqs = {c: "".join(r) for c, r in chains.items()}
    order = sorted(seqs, key=lambda c: len(seqs[c]))  # shorter chain ~ binder
    return {"file": pdb_path,
            "chains": {c: {"len": len(s), "seq": s} for c, s in seqs.items()},
            "binder_chain_guess": order[0] if order else None}


def cmd_run(a) -> None:
    root = repo_root()
    argv = build_argv(a)
    print("cwd:", root, file=sys.stderr)
    print("cmd:", " ".join(argv), file=sys.stderr)
    t0 = time.time()
    proc = subprocess.run(argv, cwd=root)
    if proc.returncode != 0:
        sys.exit(f"complexa exited with code {proc.returncode}")
    pdbs = discover_complex_pdbs(root, since=t0)
    out = Path(a.out) if a.out else None
    saved = []
    if out:
        (out / "inference").mkdir(parents=True, exist_ok=True)
        for p in pdbs:
            dest = out / "inference" / p.name
            shutil.copy2(p, dest)
            saved.append(str(dest))
        (out / "command.txt").write_text(" ".join(argv) + "\n")
    import json
    report = [extract(p) for p in (saved or [str(p) for p in pdbs])]
    print(json.dumps({"n_complexes": len(report), "binders": report}, indent=1))


def cmd_extract(a) -> None:
    import json
    print(json.dumps([extract(p) for p in a.pdb], indent=1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_run_args(sp):
        sp.add_argument("--config", default=DEFAULT_CONFIG)
        # 'generate' (default) = lean path: reward-guided search (best-of-n) already
        # AF2-selects during generation, emits co-designed seq+structure PDBs, and
        # avoids the full pipeline's redundant re-fold (evaluate) + foldseek/sc (analyze).
        # Use 'design' only if you specifically want Complexa's internal evaluate/analyze.
        sp.add_argument("--mode", choices=["design", "generate"], default="generate")
        sp.add_argument("--task-name")
        sp.add_argument("--run-name", default="complexa_run")
        sp.add_argument("--algorithm", default="best-of-n")
        sp.add_argument("--num-samples", type=int)
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--gen-njobs", type=int)
        sp.add_argument("--eval-njobs", type=int)
        sp.add_argument("--ckpt-path"); sp.add_argument("--ckpt-name")
        sp.add_argument("--autoencoder-ckpt-path")
        sp.add_argument("--cli-bin", default=os.environ.get("COMPLEXA_BIN", "complexa"))
        sp.add_argument("--override", nargs="*", help="extra ++key=value Hydra overrides")
        sp.add_argument("--out", help="copy discovered complex PDBs here")

    sp = sub.add_parser("run", help="build + run complexa, then discover/extract")
    add_run_args(sp)
    sp = sub.add_parser("extract", help="extract per-chain sequences from complex PDB(s)")
    sp.add_argument("pdb", nargs="+")

    a = p.parse_args()
    if a.cmd == "run":
        cmd_run(a)
    elif a.cmd == "extract":
        cmd_extract(a)


if __name__ == "__main__":
    main()
