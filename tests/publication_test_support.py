"""Counted transport fixtures only; no real publication or host qualification."""
import base64
import hashlib
import json
import shlex


def publication_reply(command):
    args=shlex.split(command)
    if len(args)!=5 or args[1:3]!=['-I','-c']:
        return None
    try:payload=json.loads(base64.b64decode(args[-1],validate=True))
    except (ValueError,UnicodeError):return None
    if not isinstance(payload,dict) or not {'expected','destination','upload'}<=set(payload):return None
    digest=hashlib.sha256(json.dumps(payload['expected'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return json.dumps({'path':payload['destination'],'manifest_sha256':digest,'reused':False})
