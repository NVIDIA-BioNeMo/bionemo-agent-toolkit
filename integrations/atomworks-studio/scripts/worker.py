"""Detached submission survives MCP server restarts; never retries unknown launches."""
import sys
import hashlib
from pathlib import Path
from core import Backend
b = Backend(Path(sys.argv[1]))
job = b.read(sys.argv[2], 'job.json')
source = b.state / job['snapshot_id'] / 'input.cif'
plan = b.read(job['snapshot_id'], 'plan.json')
if hashlib.sha256(source.read_bytes()).hexdigest() != plan['sha256']:
    job.update(status='failed', error='Saved input changed before submission')
    b.save_job(job)
else:
    b._submit(job['target'], job, source)
