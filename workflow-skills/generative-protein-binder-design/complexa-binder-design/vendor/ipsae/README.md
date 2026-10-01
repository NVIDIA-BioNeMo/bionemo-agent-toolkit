# vendor/ipsae

`scripts/validate_binders.py` computes **ipSAE** (interaction prediction Score from
Aligned Errors) using the canonical script from the Dunbrack lab. That script is
**third-party and not redistributed here** — fetch it once:

```bash
bash ../../scripts/fetch_ipsae.sh      # writes ipsae.py into this directory
```

This downloads `ipsae.py` to `vendor/ipsae/ipsae.py`, where the validator expects it.

## Attribution

- **Source:** <https://github.com/dunbracklab/IPSAE> (`ipsae.py`)
- **Author:** Roland L. Dunbrack Jr., Fox Chase Cancer Center
- **License:** MIT (per the script header: may be modified and redistributed for
  non-commercial and commercial use, as long as the attribution is reproduced)
- **Reference:** Dunbrack, "Rēs ipSAE loquunt: What's wrong with AlphaFold's ipTM
  score and how to fix it," bioRxiv 2025.02.10.637595.

ipSAE runs in Boltz mode here: `ipsae.py <pae.npz> <model.cif> <pae_cutoff> <dist_cutoff>`.
