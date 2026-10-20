"""Stage the synchronized public BioNeMo plugin without external/private files.

Usage: python scripts/stage_rfd4_plugin.py --output /local/plugin
The output must not exist. Model weights and development state are not included.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
repo=Path(__file__).resolve().parents[1]
if a.output.exists():p.error('Output exists; choose a new directory to preserve local work')
subprocess.run([__import__('sys').executable,str(repo/'scripts/plugin_sync.py'),'--check'],check=True)
source=repo/'skills/bionemo-agent-toolkit'
shutil.copytree(source,a.output,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.venv','node_modules'))
manifest=repo/'open-models-skills/rfd4-proteina/source-manifest.json'
shutil.copy2(manifest,a.output/'RFD4-SOURCE.json')
print(a.output.resolve())
