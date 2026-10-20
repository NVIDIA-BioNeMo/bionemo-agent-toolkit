"""Start the already-installed CPU editor, never install or start GPU compute."""
import fcntl
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit
import httpx
from editor_compat import EXPECTED_SOURCE
from editor_identity import store_identity


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
        if not python: raise ValueError('CPU editor is unavailable; configure RFD4_EDITOR_PYTHON to start it')
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
