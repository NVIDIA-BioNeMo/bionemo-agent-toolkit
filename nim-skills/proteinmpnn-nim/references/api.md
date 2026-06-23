# ProteinMPNN NIM — API Reference

## Endpoints

| Mode | Method | URL |
|---|---|---|
| Hosted | POST | `https://health.api.nvidia.com/v1/biology/ipd/proteinmpnn/predict` |
| Local Docker | POST | `http://localhost:8000/biology/ipd/proteinmpnn/predict` |
| Health (local) | GET | `http://localhost:8000/v1/health/ready` |

**IMPORTANT**: Local path has no `/v1/` prefix.

---

## Request Body Schema

All fields are optional (minimum: provide `input_pdb`).

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `input_pdb` | string | null | — | Raw PDB file content as inline string |
| `input_pdb_asset` | string | null | — | NVCF Asset ID for large PDB files; use with original filename in `input_pdb` |
| `input_pdb_chains` | array[string] | null | — | Chains to design e.g. `["A", "B"]`; if null, all chains are designed |
| `ca_only` | boolean | false | — | Enable alpha-carbon-only backbone model |
| `use_soluble_model` | boolean | false | — | Use soluble protein model variant |
| `random_seed` | integer | null | — | Set for reproducibility |
| `num_seq_per_target` | integer | 1 | 1–100 | Sequences generated per structure |
| `sampling_temp` | array[number] | null | 0.0–1.0 | Temperature array; recommended 0.1–0.3; controls diversity |
| `pssm_jsonl` | string | null | — | PSSM file content (JSONL); evolutionary information |
| `pssm_multi` | number | 0.0 | 0.0–1.0 | Balance between PSSM and model predictions |
| `pssm_threshold` | number | 0.0 | any | Filter amino acids by PSSM score |
| `pssm_bias_flag` | boolean | false | — | Enable PSSM-based bias |
| `pssm_log_odds_flag` | boolean | false | — | Transform PSSM to log-odds |
| `fixed_positions_jsonl` | string | null | — | JSONL specifying positions that stay unchanged |
| `omit_AAs` | array[string] | null | — | One-letter codes to exclude globally e.g. `["C", "M"]` |
| `omit_AA_jsonl` | string | null | — | Chain-specific amino acid exclusions (JSONL) |
| `bias_AA_jsonl` | string | null | — | Global amino acid composition biasing (JSON) |
| `bias_by_res_jsonl` | string | null | — | Position-specific biasing (JSONL) |
| `tied_positions_jsonl` | string | null | — | Enforce identical residues across positions (JSONL) |

**No string-typed numeric fields** — all numeric parameters use proper types.

---

## Response Schema

| Field | Type | Description |
|---|---|---|
| `mfasta` | string | Multi-FASTA string with all designed sequences |
| `scores` | array[float] | Log-probabilities per designed sequence (higher = more confident) |
| `probs` | array | Per-position amino acid probabilities |

### Example mfasta output

```
>T=0.1, score=1.2345, seq=0
MKTVRQERLKSIVRGPKRAKELMSIQRQAPQTTQNLDLWLQAAQDL
>T=0.1, score=1.1987, seq=1
MKTVRQERLKSIVQGPKRAKELMSIQRQAPQTTQNLDIWLQAAEDL
```

---

## Docker Reference

```bash
set -a
[ -f .env ] && . ./.env
set +a

if [ -z "${NGC_API_KEY:-}" ] && [ -n "${NVIDIA_API_KEY:-}" ]; then
  export NGC_API_KEY="$NVIDIA_API_KEY"
fi
: "${NGC_API_KEY:?Set NGC_API_KEY or NVIDIA_API_KEY in the environment or repo-root .env}"

: "${LOCAL_NIM_CACHE:?Set LOCAL_NIM_CACHE in the environment or repo-root .env}"
export NIM_TEST_GPU="${NIM_TEST_GPU:-0}"
mkdir -p "${LOCAL_NIM_CACHE}"
chmod 777 "${LOCAL_NIM_CACHE}"

docker run -it \
  --runtime=nvidia \
  --gpus "device=${NIM_TEST_GPU}" \
  -e NGC_API_KEY \
  -v "${LOCAL_NIM_CACHE}:/home/nvs/.cache/nim" \
  -p 8000:8000 \
  nvcr.io/nim/ipd/proteinmpnn:latest
```

| Flag | Value | Notes |
|---|---|---|
| `--gpus` | `device=${NIM_TEST_GPU}` | Single GPU only |
| Cache mount | `/home/nvs/.cache/nim` | **Different from other NIMs** — NOT `/opt/nim/.cache` |
| Image | `nvcr.io/nim/ipd/proteinmpnn:latest` | v1.1.0 as of 2025 |
| No `--shm-size` | — | Not required for this NIM |

---

## Annotated Example Request

```json
{
  "input_pdb": "<full PDB file content>",
  "num_seq_per_target": 10,
  "sampling_temp": [0.1],
  "use_soluble_model": false,
  "ca_only": false,
  "omit_AAs": ["C"],
  "input_pdb_chains": ["A"]
}
```

---

## Hardware Requirements

| Component | Requirement |
|---|---|
| Minimum GPU VRAM | 3 GB |
| Compute capability | >7.0 |
| CPU | 4 cores |
| RAM | 8 GB |
| Storage | 10 GB |
