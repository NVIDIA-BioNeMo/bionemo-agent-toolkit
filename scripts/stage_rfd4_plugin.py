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
for name in ('LICENSE','LICENSE-APACHE-2.0','LICENSE-CC-BY-4.0','NOTICE'):
    shutil.copy2(repo/name,a.output/name)
recipe=json.loads((repo/'integrations/atomworks-studio/scripts/runtime_recipe.json').read_text())
bundles={}
for skill in sorted((repo/'open-models-skills/rfd4-proteina').iterdir()):
    if not skill.is_dir() or not (skill/'SKILL.md').is_file():continue
    bundles[skill.name]={str(f.relative_to(skill)):hashlib.sha256(f.read_bytes()).hexdigest()
                        for f in sorted(skill.rglob('*'))
                        if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc'}
manifest={'catalog_repository':'https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit',
          'attribution':'NOTICE and each skill\'s SKILL.md and skill-card.md',
          'model_repository':'https://github.com/RosettaCommons/RFD4-Proteina',
          'model_revision':recipe['model_revision'],'skills':bundles}
(a.output/'RFD4-SOURCE.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(a.output.resolve())
