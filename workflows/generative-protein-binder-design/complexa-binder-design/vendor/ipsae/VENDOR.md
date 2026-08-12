# Vendored: ipsae.py (Dunbrack lab)

`ipsae.py` is vendored **verbatim, unmodified** so the pipeline's interface score
(ipSAE) comes from the canonical reference implementation rather than a re-derivation.

| | |
|---|---|
| **Source** | https://github.com/DunbrackLab/IPSAE |
| **File** | `https://raw.githubusercontent.com/DunbrackLab/IPSAE/main/ipsae.py` |
| **Version** | v4 (header dated "January 3, 2026: Fixed Boltz2 issues") |
| **Retrieved** | 2026-06-10 |
| **License** | MIT (per the script header: free to modify/redistribute for non-commercial and commercial use, provided the header information is reproduced) |
| **Paper** | Dunbrack, "Rēs ipSAE loquunt: What's wrong with AlphaFold's ipTM score and how to fix it", bioRxiv 2025.02.10.637595 |

## Why this version

v4 explicitly supports **Boltz / Boltz2** outputs in both PDB and mmCIF form and fixed
chain-ID handling for Boltz2 (the header notes the 2026-01-03 Boltz2 fix). The Boltz
invocation is:

```
python ipsae.py <pae.npz> <model.cif> <pae_cutoff> <dist_cutoff>
```

It reads the PAE matrix from the `.npz` key `pae`; the sibling `plddt_*.npz` and
`confidence_*.json` files are **optional** (they only affect the pDockQ and `ipTM_af`
report columns, not the ipSAE value). ipSAE depends only on `pae_cutoff` (paper
default **10**); `dist_cutoff` affects only the interface-residue count columns.

## How the pipeline calls it

`scripts/validate_binders.py` converts each Boltz2 NIM response into the file trio
ipsae.py expects (`<name>.cif`, `pae_<name>.npz`, optional `confidence_<name>.json`),
runs ipsae.py as a subprocess, and parses the `*_<pae>_<dist>.txt` output. For a
binder↔target complex it takes **`ipsae_min` = min(asym A→B, asym B→A)** of the
`ipSAE` (d0res) column. Do not edit `ipsae.py` here; re-vendor from upstream to update.
