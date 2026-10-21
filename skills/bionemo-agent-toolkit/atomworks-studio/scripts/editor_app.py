# Identify the editor session store without exposing its filesystem path.
import hashlib
from pathlib import Path


def store_identity(path):
    return hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()


# Small host compatibility fixes for the pinned AtomWorks Studio editor.
#
# AtomWorks' default atomize annotation adds derived classification fields lazily.
# When only one input needs that default, strict concatenation sees unequal fields.
# Compute those fields consistently on copies; never drop mismatched annotations.
#
import copy
import inspect

EXPECTED_SOURCE = {
    'studio_combine': '803146013549a4f265139cc3c8a2cab8a3a1a8a07d5cfc994dd0a56c0c643de9',
    'atomworks_concatenate': 'a7082201db5e41b9eaba46f3d8f1f00674ed632f464cafc41cfdd473da4a753b',
}


def verify_compatibility_sources(functions):
    actual = {name: hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()
              for name, fn in functions.items()}
    if actual != EXPECTED_SOURCE:
        raise ValueError('The editor dependency changed; qualify the Combine compatibility adapter before starting')
    return actual


def concatenate_with_classifications(arrays, **kwargs):
    from atomworks.io.utils.annotator import ensure_annotations
    from atomworks.io.utils.atom_array_plus import concatenate_atom_array_plus
    prepared = [copy.deepcopy(array) for array in arrays]
    if kwargs.get('fill_missing_standard_annotations'):
        for array in prepared:
            ensure_annotations(array, 'is_polymer', 'is_standard_aa', 'is_standard_dna', 'is_standard_rna')
    return concatenate_atom_array_plus(prepared, **kwargs)


# Start the already-installed CPU editor, never install or start GPU compute.
import fcntl
import os
import subprocess
import time
from urllib.parse import urlsplit
import httpx
import importlib.util
import socket
import sys


def default_editor_url(root):
    """Persist one loopback endpoint per workspace, shared by both MCP servers."""
    from upgrade_state import require_workspace_activation
    require_workspace_activation(root)
    root = Path(root)
    with (root/'editor-config.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        config = root/'editor.json'
        if config.exists():
            return json.loads(config.read_text())['studio_url']
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            url = f'http://127.0.0.1:{listener.getsockname()[1]}'
        # The startup health/identity checks still reject a foreign listener
        # if something acquires this port before the editor starts.
        temporary = root/'editor.json.tmp'
        temporary.write_text(json.dumps({'studio_url': url})+'\n')
        temporary.chmod(0o600)
        temporary.replace(config)
        return url




def ensure_editor(service):
    from upgrade_state import require_workspace_activation
    require_workspace_activation(service.root)
    python=os.environ.get('RFD4_EDITOR_PYTHON')
    url=service.studio_url()
    parsed=urlsplit(url)
    port=parsed.port or 80
    def healthy():
        try:
            result=httpx.get(url+'/api/v1/health',timeout=1,trust_env=False)
        except httpx.ConnectError: return False
        except httpx.TimeoutException as error:
            raise RuntimeError('The existing CPU editor did not respond in time; retry the connection without starting another editor') from error
        result.raise_for_status()
        if result.json().get('version')!='0.0.1':
            raise ValueError('The editor port is occupied by an unexpected service; restart the intended editor on its configured loopback port')
        compatibility=httpx.get(url+'/rfd4/compatibility',timeout=1,trust_env=False)
        if (compatibility.status_code!=200 or compatibility.json().get('adapter')!='rfd4-editor-1'
                or compatibility.json().get('sources')!=EXPECTED_SOURCE):
            raise ValueError('The editor needs the current RFD4 compatibility adapter; restart the plugin-managed editor on its configured loopback port')
        if compatibility.json().get('store_identity')!=store_identity(service.root/'editor-sessions'):
            raise ValueError('The editor belongs to another workspace; refusing to reuse its session store')
        return True
    with (service.root/'editor.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        if healthy(): return
        if not python and importlib.util.find_spec('annotation_studio') is not None:
            python = sys.executable
        if not python:
            raise ValueError('CPU editor dependencies are missing from this custom Python environment; install editor-requirements.txt or configure RFD4_EDITOR_PYTHON')
        if not Path(python).is_file(): raise ValueError('The configured CPU Studio Python is unavailable')
        env=dict(os.environ,RFD4_STUDIO_HOME=str(service.root),
                 ANNOTATION_STUDIO_SESSION_DIR=str(service.root/'editor-sessions'))
        log=service.root/'editor.log'
        with log.open('a') as output:
            process=subprocess.Popen([python,str(Path(__file__).with_name('editor_app.py')),'--port',str(port)],
                stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True,env=env)
        log.chmod(0o600)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if healthy(): return
            if process.poll() is not None: raise RuntimeError('CPU Studio could not start; inspect editor.log')
            time.sleep(.25)
        raise RuntimeError('CPU Studio is still starting; reopen the app to reconnect')


# Bounded Studio editor API bridge; never a general HTTP or command proxy.
import json
import re
from urllib.parse import urlsplit, parse_qs

READ_SUFFIX = r'(?:cif|bonds|distance-restraints|atom-distance|annotations/[A-Za-z0-9_]+|annotation-fields/[A-Za-z0-9_]+|scalar-fields/[A-Za-z0-9_]+|atoms/[0-9]+/annotations)'
WRITE_SUFFIX = r'(?:export|validate|conditions(?:/reset)?|groups|centroids|distance-restraints(?:/replace)?|protonate|charges|chains|bonds(?:/infer-ccd)?|internal-coords(?:/clear-targets)?|delete|segments(?:/realize|/collapse)?|reset-residue-ids|undo|combine|interactions/analyze|selections/(?:resolve|query))'

def validate_route(method,path):
    url=urlsplit(path)
    if url.scheme or url.netloc or url.fragment or '%' in url.path or '..' in url.path: raise ValueError('Only Studio editor API paths are allowed')
    p=url.path
    session=r'/api/v1/sessions/[A-Za-z0-9_-]{1,96}'
    allowed=(method=='GET' and (re.fullmatch(r'/api/v1/(?:schema|health|ready|examples(?:/[A-Za-z0-9_-]+/cif)?)',p) or re.fullmatch(session+r'(?:/'+READ_SUFFIX+r')?',p))) or (method=='POST' and (p in ('/api/v1/sessions','/api/v1/import/inspect') or re.fullmatch(session+'/'+WRITE_SUFFIX,p)))
    allowed = allowed or (method=='DELETE' and re.fullmatch(session,p))
    if not allowed: raise ValueError('Unsupported Studio editor operation')
    if url.query and (not p.endswith('/atom-distance') or set(parse_qs(url.query))-{'atom1','atom2'}): raise ValueError('Unsupported Studio query')

def request(service, method, path, body=None, form=None):
    validate_route(method,path)
    pass
    ensure_editor(service)
    if len(json.dumps([body,form])) > 28000000: raise ValueError('Studio request too large')
    if body is not None and form is not None: raise ValueError('Use one request body')
    kwargs={}
    if form is not None:
        files=[]; data={}
        for field in form:
            if field['name']=='file':
                text=field['value']
                if len(text.encode())>20000000: raise ValueError('CIF too large')
                filename=re.sub(r'[^A-Za-z0-9_.-]','_',field.get('filename','structure.cif'))[:120]
                files.append(('file',(filename,text,'chemical/x-mmcif')))
            elif field['name'] in ('parse_preset','assembly','advanced_options'): data[field['name']]=str(field['value'])
            else: raise ValueError('Unsupported import option')
        kwargs={'files':files,'data':data}
    elif body is not None: kwargs={'json':body}
    with httpx.Client(base_url=service.studio_url(),timeout=60,trust_env=False,follow_redirects=False) as client:
        response=client.request(method,path,**kwargs)
        if len(response.content)>30000000: raise ValueError('Studio response too large')
        return {'status':response.status_code,'content_type':response.headers.get('content-type','text/plain'),'text':response.text}


# Launch the pinned upstream editor with explicit, isolated host compatibility.
import argparse



COMPATIBILITY = 'rfd4-editor-1'

def create_app():
    directory=os.environ.get('ANNOTATION_STUDIO_SESSION_DIR')
    if not directory: raise ValueError('The managed editor requires an explicit session directory')
    from pathlib import Path
    from upgrade_state import require_workspace_activation
    root=Path(os.environ.get('RFD4_STUDIO_HOME',str(Path(directory).parent)))
    if Path(directory).resolve()!=root.resolve()/'editor-sessions':
        raise ValueError('Managed editor sessions must belong to the configured workspace')
    require_workspace_activation(root)
    owner=store_identity(directory)
    from atomworks_studio_editing import document
    from atomworks.io.utils.atom_array_plus import concatenate_atom_array_plus
    sources = verify_compatibility_sources({
        'studio_combine': document.StudioDocument.combine,
        'atomworks_concatenate': concatenate_atom_array_plus,
    })
    from annotation_studio.main import app
    document.concatenate_atom_array_plus = concatenate_with_classifications
    install_compatibility_route(app, owner, sources)
    return app


def install_compatibility_route(app, owner, sources):
    # Public Studio mounts its static frontend last. Append-only registration
    # would put this receipt behind that catch-all.
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def compatibility(request):
        return JSONResponse({'adapter': COMPATIBILITY, 'sources': sources, 'store_identity': owner})

    app.router.routes[:] = [route for route in app.router.routes
                           if route.name != 'rfd4_compatibility']
    app.router.routes.insert(0, Route('/rfd4/compatibility', compatibility,
                                    methods=['GET'], name='rfd4_compatibility'))


if __name__ == '__main__':
    import uvicorn
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    uvicorn.run(create_app(),host='127.0.0.1',port=args.port)
