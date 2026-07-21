#!/usr/bin/env bash
# =============================================================================
# launch_fast.sh — one-command fast launch of the MSA-Search NIM.
#
# Wraps the two-step fast path into a single command:
#   1. Download the requested database in parallel with aria2c (if not already present)
#   2. Start the NIM against those files via NIM_MODEL_NAME (skips the slow built-in download)
#
# Idempotent: if the database dir already holds the DB, it skips straight to launch
#             (~20 s warm start, no re-download).
#
# WHY THIS EXISTS: a plain `docker run ... -e NIM_MODEL_PROFILE=...` uses the NIM's
# built-in per-file downloader, which stalls on large DBs at the NGC per-connection
# throttle (>80 min for UniRef30). aria2c range-parallel download + NIM_MODEL_NAME
# brings that to ~14 min cold / ~20 s warm. The NIM cannot call aria2c itself, so this
# wrapper is the entry point that makes the fast path automatic.
#
# PREREQUISITES: NVIDIA GPU + Docker + NVIDIA runtime; NGC_API_KEY with nvcr.io pull
#                scope; ~600 GB free NVMe for UniRef30; docker, curl, python3 (installs
#                aria2c if missing).
#
# USAGE:
#   export NGC_API_KEY=nvapi-...
#   ./launch_fast.sh                      # defaults: UniRef30 -> /data/fast-db, port 8000
#   ./launch_fast.sh -m colabfold_envdb_202108-m18v1 -d /data/envdb -p 8001
#
# OPTIONS:
#   -m  NGC DB model version   (default: uniref30_2302-m18v1)
#   -d  local DB directory     (default: /data/fast-db)
#   -p  host port              (default: 8000)
#   -n  container name         (default: msa-search)
#   -s  aria2 split / conns    (default: 16)
#   -c  aria2 concurrent files (default: 4)
# =============================================================================
set -uo pipefail

MODEL_VERSION=uniref30_2302-m18v1
DBDIR=/data/fast-db
PORT=8000
NAME=msa-search
SPLIT=16
CONC=4
IMG=nvcr.io/nim/colabfold/msa-search:2

while getopts "m:d:p:n:s:c:h" opt; do
  case $opt in
    m) MODEL_VERSION=$OPTARG ;;
    d) DBDIR=$OPTARG ;;
    p) PORT=$OPTARG ;;
    n) NAME=$OPTARG ;;
    s) SPLIT=$OPTARG ;;
    c) CONC=$OPTARG ;;
    h) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "bad option; -h for help"; exit 2 ;;
  esac
done

: "${NGC_API_KEY:?export NGC_API_KEY (with nvcr.io pull scope) first}"
log(){ echo -e "\n=== $* ==="; }

# The DB short-name is the model version without the -m##v# suffix (e.g. uniref30_2302).
DBNAME=$(echo "$MODEL_VERSION" | sed -E 's/-m[0-9]+v[0-9]+$//')

# -----------------------------------------------------------------------------
# STEP 1: download (skipped if the DB's .idx already exists locally)
# -----------------------------------------------------------------------------
if ls "$DBDIR/$DBNAME/"*_db.idx >/dev/null 2>&1; then
  log "DB already present in $DBDIR/$DBNAME — skipping download (warm start)"
else
  log "Downloading $MODEL_VERSION into $DBDIR with aria2c (${CONC}x${SPLIT})"
  command -v aria2c >/dev/null || sudo apt-get install -y aria2
  mkdir -p "$DBDIR"

  curl -fsS -H "Authorization: Bearer $NGC_API_KEY" \
    "https://api.ngc.nvidia.com/v2/org/nim/team/colabfold/models/msa-search/${MODEL_VERSION}/files" \
    -o /tmp/files.json || { echo "NGC files API call failed"; exit 1; }

  DBDIR="$DBDIR" python3 - <<'PY'
import json, os
d = json.load(open("/tmp/files.json"))
dbdir = os.environ["DBDIR"]
lines = []
for url, path in zip(d["urls"], d["filepath"]):
    lines += [url.strip(), f"  dir={dbdir}", f"  out={path}"]
open("/tmp/aria.in", "w").write("\n".join(lines) + "\n")
print(f"files to fetch: {len(d['urls'])}")
PY

  T0=$(date +%s)
  aria2c -i /tmp/aria.in \
    --max-concurrent-downloads="$CONC" \
    --max-connection-per-server="$SPLIT" \
    --split="$SPLIT" \
    --min-split-size=1M --continue=true --file-allocation=none \
    --summary-interval=30 --console-log-level=warn
  RC=$?
  [ $RC -eq 0 ] || { echo "aria2c failed (exit $RC)"; exit $RC; }
  echo "download_seconds=$(( $(date +%s) - T0 ))  size=$(du -sh "$DBDIR" | cut -f1)"
  rm -f /tmp/files.json /tmp/aria.in
fi

# -----------------------------------------------------------------------------
# STEP 2: launch the NIM against the downloaded files
# -----------------------------------------------------------------------------
log "Launching NIM ($NAME) on port $PORT against $DBDIR"
docker rm -f "$NAME" >/dev/null 2>&1 || true
S0=$(date +%s)
docker run -d --name "$NAME" --runtime=nvidia --gpus all \
  -e NGC_API_KEY \
  -e NIM_MODEL_NAME=/databases \
  -v "$DBDIR:/databases" \
  -p "${PORT}:8000" \
  "$IMG" >/dev/null

log "Waiting for readiness"
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:${PORT}/v1/health/ready)" = "200" ]; do
  sleep 3
  docker ps --filter "name=$NAME" --format '{{.Names}}' | grep -q "$NAME" \
    || { echo "container exited:"; docker logs "$NAME" | tail -30; exit 1; }
done
echo "READY after $(( $(date +%s) - S0 )) s"
echo "Loaded DB: $(curl -s http://localhost:${PORT}/biology/colabfold/msa-search/config/msa-database-configs)"
echo
echo "Endpoint: http://localhost:${PORT}/biology/colabfold/msa-search/{predict,paired/predict}"
echo "Tip: persist $DBDIR (snapshot the volume) so future launches skip the download entirely."
