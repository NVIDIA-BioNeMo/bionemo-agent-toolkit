"""Start the already-installed CPU editor, never install or start GPU compute."""
import fcntl
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit
import httpx


def ensure_editor(service):
    python=os.environ.get('RFD4_EDITOR_PYTHON')
    if not python: return
    if not Path(python).is_file(): raise ValueError('The configured CPU Studio Python is unavailable')
    url=service.studio_url()
    parsed=urlsplit(url)
    port=parsed.port or 80
    def healthy():
        try:
            result=httpx.get(url+'/api/v1/health',timeout=1,trust_env=False)
        except httpx.ConnectError: return False
        result.raise_for_status()
        if result.json().get('version')!='0.1.0':
            raise ValueError('The editor port is occupied by an unexpected service; choose a separate loopback port')
        return True
    with (service.root/'editor.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        if healthy(): return
        env=dict(os.environ,ANNOTATION_STUDIO_SESSION_DIR=str(service.root/'editor-sessions'))
        log=service.root/'editor.log'
        with log.open('a') as output:
            process=subprocess.Popen([python,'-m','uvicorn','annotation_studio.main:app','--host','127.0.0.1','--port',str(port)],
                stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True,env=env)
        log.chmod(0o600)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if healthy(): return
            if process.poll() is not None: raise RuntimeError('CPU Studio could not start; inspect editor.log')
            time.sleep(.25)
        raise RuntimeError('CPU Studio is still starting; reopen the app to reconnect')
