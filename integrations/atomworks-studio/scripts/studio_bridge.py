"""Bounded Studio editor API bridge; never a general HTTP or command proxy."""
import json
import re
from urllib.parse import urlsplit, parse_qs
import httpx

READ_SUFFIX = r'(?:cif|bonds|distance-restraints|atom-distance|annotations/[A-Za-z0-9_]+|annotation-fields/[A-Za-z0-9_]+|scalar-fields/[A-Za-z0-9_]+|atoms/[0-9]+/annotations)'
WRITE_SUFFIX = r'(?:export|validate|conditions|groups|centroids|distance-restraints(?:/replace)?|protonate|charges|chains|bonds(?:/infer-ccd)?|internal-coords(?:/clear-targets)?|delete|segments(?:/realize|/collapse)?|reset-residue-ids|undo|combine|interactions/analyze|selections/(?:resolve|query))'

def validate_route(method,path):
    url=urlsplit(path)
    if url.scheme or url.netloc or url.fragment or '%' in url.path or '..' in url.path: raise ValueError('Only Studio editor API paths are allowed')
    p=url.path
    session=r'/api/v1/sessions/[A-Za-z0-9_-]{1,96}'
    allowed=(method=='GET' and (re.fullmatch(r'/api/v1/(?:schema|health|ready|examples(?:/[A-Za-z0-9_-]+/cif)?)',p) or re.fullmatch(session+r'(?:/'+READ_SUFFIX+r')?',p))) or (method=='POST' and (p=='/api/v1/sessions' or re.fullmatch(session+'/'+WRITE_SUFFIX,p)))
    if not allowed: raise ValueError('Unsupported Studio editor operation')
    if url.query and (not p.endswith('/atom-distance') or set(parse_qs(url.query))-{'atom1','atom2'}): raise ValueError('Unsupported Studio query')

def request(service, method, path, body=None, form=None):
    validate_route(method,path)
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
