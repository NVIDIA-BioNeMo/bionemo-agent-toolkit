"""Optional adapter to the installed NGS Workbench registry, never a copied catalog.

Set NGS_WORKBENCH_MCP_ROOT to that plugin's mcp directory. Use its own
authenticated client, target schema and SSH identity resolver. No registry
files, tokens or credentials are exposed to the app.
"""
import os
from pathlib import Path
import sys
import subprocess
import json


def request(path, payload):
    """Let NGS start its daemon using its own complete runtime dependencies."""
    if path not in ('/targets', '/targets/inspect'): raise ValueError('Unsupported registry operation')
    root=Path(os.environ['NGS_WORKBENCH_MCP_ROOT']).expanduser().resolve()
    version=(root/'PLUGIN_VENV_VERSION').read_text().strip()
    if not version or '/' in version or '..' in version: raise ValueError('Invalid NGS runtime version')
    codex=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
    python=codex/'cache/ngs-analysis-workbench/venvs'/version/'bin/python'
    if not python.is_file(): raise ValueError('Open NGS Workbench once to initialize its compute registry runtime')
    env=dict(os.environ, PYTHONPATH=str(root))
    code="import json,sys; from ngs_workbench_daemon import client; v=json.load(sys.stdin); print(json.dumps(client.request(v['path'],v['payload'],role='compute',timeout=25)))"
    result=subprocess.run([str(python),'-c',code],input=json.dumps({'path':path,'payload':payload}),capture_output=True,text=True,timeout=50,env=env,cwd=root)
    if result.returncode: raise ValueError('NGS registry unavailable: '+result.stderr[-1500:])
    return json.loads(result.stdout)


def modules():
    root = os.environ.get('NGS_WORKBENCH_MCP_ROOT')
    if not root:
        raise ValueError('NGS Workbench registry is not connected. Existing SSH and Brev setup remain available in chat.')
    path = Path(root).expanduser().resolve()
    if not (path / 'ngs_workbench_daemon/client.py').is_file():
        raise ValueError('NGS Workbench MCP directory is unavailable')
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    from ngs_workbench_daemon import client, inspection
    from ngs_workbench_daemon.protocol import LOCAL_TARGET_PAYLOAD
    from ngs_workbench_daemon.state import daemon_directory
    from ngs_workbench_mcp.compute_targets import ComputeTarget
    return client, inspection, LOCAL_TARGET_PAYLOAD, daemon_directory, ComputeTarget


def targets():
    client, _, local, directory, model = modules()
    # Match NGS's own list_compute_targets: an absent registry is not an error.
    values = ([local] if client.healthy_daemon() is None and
              not (directory(create=False) / 'targets.json').is_file()
              else request('/targets', {})['targets'])
    return [model.model_validate(value).model_dump(mode='json') for value in values]


def resolve(target_id):
    for target in targets():
        if target['target_id'] == target_id:
            if target['executor'] != 'local_process':
                raise ValueError('This target uses Slurm; RFD4 direct execution does not support it yet. Choose a direct GPU host in chat.')
            if target['controller_transport'] not in ('ssh', 'local_process'):
                raise ValueError('Unsupported compute transport')
            return target
    raise ValueError('The selected NGS compute target no longer exists')


def verify(reference, *, require_registry=True):
    # New submissions must resolve the current catalog. Existing jobs stay bound
    # to their saved target even if a different target is selected or removed.
    if require_registry:
        current = resolve(reference['target_id'])
        if current != reference:
            raise ValueError('NGS compute configuration changed; select the target and review again')
    if reference['controller_transport'] == 'ssh':
        _, inspection, _, _, _ = modules()
        if inspection.effective_access(reference['host_access']['alias']) != reference['host_access']:
            raise ValueError('SSH identity changed since this target was registered. Reconnect in chat before continuing.')


def inspect(target_id):
    return request('/targets/inspect', {'target_id': target_id, 'executable_paths': []})
