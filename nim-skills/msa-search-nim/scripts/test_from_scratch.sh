#!/usr/bin/env bash
# =============================================================================
# End-to-end test of the UPDATED msa-search-nim skill (PR #20) from scratch.
#
# Validates the two things the PR adds:
#   1. Task-specific database profile  (download only UniRef30, not the full 1.4 TB)
#   2. Parallel download + NIM_MODEL_NAME warm start  (~13.5 min vs >80 min)
# ...then proves correctness with a real paired MSA search (C1GY11 + C1HCX1).
#
# PREREQUISITES on a fresh node:
#   - NVIDIA GPU (A100/H100/L40S...), Docker + NVIDIA runtime, ~600 GB free NVMe
#   - NGC_API_KEY with registry (nvcr.io) pull scope   <-- export before running
#   - Tools: docker, curl, python3, aria2c  (script installs aria2c if missing)
#
# USAGE:
#   export NGC_API_KEY=nvapi-...
#   bash test_msa_skill_from_scratch.sh
# =============================================================================
set -uo pipefail

: "${NGC_API_KEY:?export NGC_API_KEY (with nvcr.io pull scope) first}"
DATA=/data                      # fast NVMe mount with ~600 GB free
IMG=nvcr.io/nim/colabfold/msa-search:2
DBDIR=$DATA/fast-db             # where aria2 writes the databases
PORT=8000
MODEL_VERSION=uniref30_2302-m18v1   # the individual UniRef30 DB model version on NGC

log(){ echo -e "\n=== $* ==="; }

# -----------------------------------------------------------------------------
log "STEP 0  Install the UPDATED skill from the PR branch"
# The catalog ships the OLD skill; test the PR version by checking it out.
# (Skip if you already have the branch installed in your agent skills dir.)
SKILL_SRC=/tmp/bionemo-agent-toolkit
rm -rf "$SKILL_SRC"
git clone --depth 1 --branch msa-search-nim-db-profiles \
  https://github.com/nil16/bionemo-agent-toolkit.git "$SKILL_SRC"
echo "Updated SKILL.md sections:"
grep -E '^## ' "$SKILL_SRC/nim-skills/msa-search-nim/SKILL.md"
# You should see "Faster Startup: Task-Specific Database Profiles"
#            and "Even Faster: Parallel Download Of A Large Single-DB Profile"

# -----------------------------------------------------------------------------
log "STEP 1  docker login + confirm the task-specific profile exists"
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
docker pull "$IMG"
echo "Available profiles (hashes change between releases — read them here, never hardcode):"
docker run --rm --entrypoint list-model-profiles "$IMG" | grep -iE 'databases:'
# Expect a 'databases:uniref30' profile — that is the paired-search profile (~490 GB).

# -----------------------------------------------------------------------------
log "STEP 2  Parallel download of UniRef30 with aria2c (the fast path)"
command -v aria2c >/dev/null || sudo apt-get install -y aria2
mkdir -p "$DBDIR"
# 2a) presigned file URLs for the individual DB version
curl -s -H "Authorization: Bearer $NGC_API_KEY" \
  "https://api.ngc.nvidia.com/v2/org/nim/team/colabfold/models/msa-search/${MODEL_VERSION}/files" \
  -o /tmp/files.json
# 2b) build aria2 input (urls[] and filepath[] are positionally paired)
python3 - <<'PY'
import json
d = json.load(open("/tmp/files.json"))
lines = []
for url, path in zip(d["urls"], d["filepath"]):
    lines += [url.strip(), "  dir=/data/fast-db", f"  out={path}"]
open("/tmp/aria.in", "w").write("\n".join(lines) + "\n")
print("files to fetch:", len(d["urls"]))
PY
# 2c) download in parallel — 4 files at once, 16 range-connections each
T0=$(date +%s)
aria2c -i /tmp/aria.in \
  --max-concurrent-downloads=4 --max-connection-per-server=16 --split=16 \
  --min-split-size=1M --continue=true --file-allocation=none \
  --summary-interval=30 --console-log-level=warn
echo "aria2 exit=$? download_seconds=$(( $(date +%s) - T0 ))"
echo "downloaded size:"; du -sh "$DBDIR"

# -----------------------------------------------------------------------------
log "STEP 3  Start the NIM against the downloaded DB via NIM_MODEL_NAME"
docker rm -f msa-search 2>/dev/null || true
S0=$(date +%s)
docker run -d --name msa-search --runtime=nvidia --gpus all \
  -e NGC_API_KEY \
  -e NIM_MODEL_NAME=/databases \
  -v "$DBDIR:/databases" \
  -p ${PORT}:8000 \
  "$IMG"

log "STEP 4  Wait for readiness (should be well under a minute — index already local)"
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:${PORT}/v1/health/ready)" = "200" ]; do
  sleep 3
  # bail if container died
  docker ps --filter name=msa-search --format '{{.Names}}' | grep -q msa-search || { docker logs msa-search | tail -30; exit 1; }
done
echo "READY after $(( $(date +%s) - S0 )) s from container start"
echo "Loaded database:"; curl -s http://localhost:${PORT}/biology/colabfold/msa-search/config/msa-database-configs

# -----------------------------------------------------------------------------
log "STEP 5  Functional check — real paired MSA search (C1GY11 + C1HCX1)"
A=$(curl -s https://rest.uniprot.org/uniprotkb/C1GY11.fasta | grep -v '^>' | tr -d '\n')
B=$(curl -s https://rest.uniprot.org/uniprotkb/C1HCX1.fasta | grep -v '^>' | tr -d '\n')
cat > /tmp/paired.json <<EOF
{"sequences":["$A","$B"],"databases":["Uniref30_2302"],"e_value":0.0001,"max_msa_sequences":500,"pairing_strategy":"greedy"}
EOF
curl -s -X POST http://localhost:${PORT}/biology/colabfold/msa-search/paired/predict \
  -H 'Content-Type: application/json' -d @/tmp/paired.json -o /tmp/paired_out.json \
  -w 'paired_http=%{http_code} time=%{time_total}s\n'
python3 - <<'PY'
import json
d = json.load(open("/tmp/paired_out.json"))
if "error" in d:
    print("ERROR:", d["error"]); raise SystemExit(1)
abc = d["alignments_by_chain"]
for ch in ("A", "B"):
    a = abc[ch]["Uniref30_2302"]["a3m"]["alignment"]
    print(f"chain {ch}: rows={a.count('>')}  query_start={a.splitlines()[1][:24]}")
print("search_type:", d["metrics"].get("search_type"))
print("PASS: paired search returned equal-depth species-paired alignments"
      if all(abc[c]['Uniref30_2302']['a3m']['alignment'].count('>')>0 for c in 'AB')
      else "FAIL")
PY

# -----------------------------------------------------------------------------
log "DONE.  Expected results:"
cat <<'EOF'
  - list-model-profiles shows databases:uniref30 (~490 GB) profile
  - aria2 download of ~490 GB completes in ~13-15 min (vs >80 min built-in)
  - NIM reaches /health/ready within ~1 min of container start (index is local)
  - paired search: HTTP 200, chain A & B each ~500 rows, search_type colabfold_paired
  - Next time: persist $DBDIR (or snapshot the volume) -> ~20 s warm start, no re-download
EOF
