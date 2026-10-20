"""Local development host for the SAME self-contained MCP app HTML."""
import asyncio
import os
import json
from pathlib import Path
import secrets
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from service import Service

service = Service()
TOKEN = secrets.token_urlsafe(32)
PORT = int(os.environ.get('RFD4_PREVIEW_PORT', '8766'))
ORIGIN = f'http://127.0.0.1:{PORT}'
# Mirrors the no-iframe, no-external-script environment of the embedded app.
CSP = "default-src 'none'; script-src 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'self'; frame-src 'none'; worker-src blob:; font-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"

def load_demo(): return service.viewer_payload(service.load_demo())
def import_structure(cif): return service.viewer_payload(service.import_cif(cif))
def open_result(job_id):
    service.collect(job_id)
    return service.viewer_payload(service.open_result(job_id))
def execute_plan(**arguments): return service.public_job(service.execute(**arguments))
def job_status(job_id): return service.public_job(service.status(job_id))
ALLOWED = {'get_compute_capabilities':service.capabilities,'select_compute':lambda **kw:service.register_registry_compute(**kw),'inspect_compute_target':service.inspect_compute_target,'disconnect_compute':service.disconnect_compute,'open_run_structure':service.open_run_structure,'list_results':service.results,'download_results':service.download_results,'load_demo':load_demo,'import_structure':import_structure,'open_result':open_result,
           'refresh_selected_compute_access':service.refresh_selected_compute_access,'begin_compute_setup':service.begin_setup,'save_draft':service.save_draft,'list_drafts':service.list_drafts,'restore_draft':service.restore_draft,'list_registered_compute':service.available_compute,
           'get_workspace':service.overview,'resolve_selection':service.resolve_selection,
           'set_condition':service.set_condition,'prepare_design':service.prepare,
           'studio_request':lambda **kw: __import__('studio_bridge').request(service,**kw),'get_compute_status':service.compute_status,'check_compute':service.check_compute,'execute_rfd4_plan':execute_plan,'check_rfd4_job':job_status}

async def index(request):
    asset=Path(__file__).parents[1]/'assets/studio-upstream.html'
    html=asset.read_text()
    return HTMLResponse(html.replace('/*LOCAL_CONFIG*/',f'window.localToken={json.dumps(TOKEN)};'),
        headers={'Cache-Control':'no-store','Content-Security-Policy':CSP,'X-Content-Type-Options':'nosniff'})

async def call(request: Request):
    if request.headers.get('origin') != ORIGIN or request.headers.get('x-rfd4-token') != TOKEN:
        return JSONResponse({'isError':True,'error':'Invalid local request'},status_code=403)
    try:
        body=await request.body()
        if len(body)>30000000: raise ValueError('Request too large')
        payload=json.loads(body)
        if payload['name'] not in ALLOWED: raise ValueError('Unknown tool')
        result=await asyncio.to_thread(ALLOWED[payload['name']],**payload.get('arguments',{}))
        return JSONResponse({'structuredContent':result})
    except Exception as error:
        return JSONResponse({'isError':True,'content':[{'type':'text','text':str(error)}]})

app=Starlette(routes=[Route('/',index),Route('/api/tools',call,methods=['POST'])],
    middleware=[Middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1'])])
if __name__=='__main__': uvicorn.run(app,host='127.0.0.1',port=PORT)
