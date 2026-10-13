"""Stage a local BioNeMo plugin with EXISTING RFD4 skills, without rewriting them.

Usage: python scripts/stage_rfd4_plugin.py --model-repo /authorized/RFD4 --output /local/plugin
The output must not exist. It includes evaluation-licensed files and is for local use.
"""
import argparse
import json
import shutil
import subprocess
import hashlib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--model-repo',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
repo=Path(__file__).resolve().parents[1]
model=a.model_repo.resolve()
if not (model/'skills/rfd4-proteina-generate/SKILL.md').is_file():
    p.error('Expected the existing RFD4 skill catalog in the authorized model checkout')
if a.output.exists():
    p.error('Output exists; choose a new directory to preserve local work')
shutil.copytree(repo/'skills/bionemo-agent-toolkit',a.output,ignore=shutil.ignore_patterns('__pycache__','.venv'))
for skill in (model/'skills').iterdir():
    if skill.is_dir() and (skill/'SKILL.md').is_file():
        shutil.copytree(skill,a.output/'skills'/skill.name)
# Existing relative documentation references resolve from inside each skill.
shutil.copytree(model/'docs',a.output/'docs')
shutil.copy2(model/'LICENSE',a.output/'RFD4-EVALUATION-LICENSE')
shutil.copy2(model/'skills/README.md',a.output/'RFD4-SKILLS-README.md')
revision=subprocess.check_output(['git','-C',str(model),'rev-parse','HEAD'],text=True).strip()
hashes={str(f.relative_to(model)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (model/'skills').rglob('*') if f.is_file() and '__pycache__' not in f.parts}
(a.output/'RFD4-SOURCE.json').write_text(json.dumps({'model_repository':str(model),'revision':revision,'skill_sha256':hashes,'instructions':'Upstream skills copied unchanged. Run model commands from the configured model repository, as those skills specify. Local evaluation only; do not publish this staged bundle.'},indent=2)+'\n')
print(a.output.resolve())
