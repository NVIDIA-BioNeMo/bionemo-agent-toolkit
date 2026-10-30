"""Embedded editing and chat-led execution on explicitly named SSH hosts."""
import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from service import Service

service = Service()
URI = 'ui://bionemo-rfd4/studio.html'
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
APP = {'ui':{'visibility':['app']}}
REVIEW = {'ui':{'resourceUri':URI,'visibility':['app','model']}}
mode = sys.argv[1] if len(sys.argv)>1 else 'app'
mcp = FastMCP('rfd4-studio-' + mode)
@mcp.resource(URI, name='rfd4-studio', title='RFD4-Proteina Studio', mime_type='text/html;profile=mcp-app', meta={
    'ui':{'csp':{'connectDomains':[], 'resourceDomains':[], 'frameDomains':[]},'supportsFullscreen':True},
    'openai/ui':{'availableDisplayModes':['inline','fullscreen']},
    'openai/widgetCSP':{'connectDomains':[], 'resourceDomains':[], 'frameDomains':[]},
    'openai/widgetSupportsFullscreen':True,
    'openai/widgetAccessible':True,
})
def panel():
    asset=Path(__file__).parents[1]/'assets/studio-upstream.html'
    if not asset.exists(): raise RuntimeError('Build the pinned upstream Studio frontend first; see the adapter README.')
    return asset.read_text()

@mcp.tool(meta={'ui':{'visibility':['app','model']}} if mode == 'app' else {}, annotations=READ)
def get_rfd4_export(export_id: str) -> dict:
    """Verify a saved export and return its local path. Share it as a Markdown file link; no compute is contacted."""
    from local_exports import get
    return get(service.root,export_id)

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=WRITE)
def prepare_design_request(session_id: str, note: str='', samples: int=1, seed: int=42, image_base64: str | None=None, generation: dict | None=None) -> dict:
    """Save and validate an immutable design request. No compute selection or provisioning is required."""
    return service.prepare_design_request(session_id,note,samples,seed,image_base64,generation)

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=READ)
def get_design_request(request_id: str) -> dict:
    """Read and verify a saved design request before choosing its execution host in chat."""
    return service.get_design_request(request_id)

if mode != 'app':
    @mcp.tool(annotations=READ)
    def get_target_suggestions() -> dict:
        """Read last chosen or legacy SSH targets as unverified suggestions; never selects or probes a machine."""
        return service.target_suggestions()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def collect_design_results(job_id: str) -> dict:
        """Retrieve verified results and terminal logs before any chat-authorized shutdown."""
        return service.collect(job_id)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
    def check_named_target(target: dict) -> dict:
        """Check an explicitly named SSH host and public RFD4 runtime. Does not create or start machines."""
        return service.check_named_target(target)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def submit_design_request(request_id: str, target: dict, compute_note: str="") -> dict:
        """Submit immutable input to a named host within this call. Repeated requests reconcile the same remote job."""
        return service.public_job(service.submit_design_request(request_id, target, compute_note))

if mode == 'app':

    @mcp.tool(meta=APP, annotations=WRITE)
    def save_rfd4_export(filename: str, mime_type: str, text: str | None=None, base64_data: str | None=None) -> dict:
        """Save the exact clicked CIF/ZIP locally for export through chat; never starts compute."""
        from local_exports import save
        return save(service.root,filename,mime_type,text,base64_data)

    @mcp.tool(meta=APP, annotations=WRITE)
    def save_draft(session_id: str, note: str='', image_base64: str | None=None, settings: dict | None=None) -> dict:
        """Persist the annotated CIF and notes before leaving the editor, including incomplete designs."""
        return service.save_draft(session_id,note,image_base64,settings)

    @mcp.tool(meta=APP, annotations=READ)
    def list_drafts() -> dict:
        """List locally saved drafts for explicit recovery after a reload."""
        return service.list_drafts()

    @mcp.tool(meta=APP, annotations=WRITE)
    def restore_draft(draft_id: str, expected_checksum: str | None=None) -> dict:
        """Reopen a saved draft as a new Studio session."""
        return service.restore_draft(draft_id, expected_checksum)
    @mcp.tool(meta=APP, annotations=WRITE)
    def studio_request(method: str, path: str, body: dict | None=None, form: list[dict] | None=None) -> dict:
        """Run an allowlisted Studio editor operation against the configured loopback service."""
        from editor_app import request
        return request(service,method,path,body,form)

    @mcp.tool(title='RFD4-Proteina Studio', meta={'ui/resourceUri':URI,'openai/outputTemplate':URI,'openai/widgetAccessible':True,'ui':{'resourceUri':URI,'visibility':['app','model'],'supportsFullscreen':True}}, annotations=READ)
    def open_rfd4_studio() -> dict:
        """Open AtomWorks Studio inline in this conversation. The user may expand it beside the chat. Call this when asked to open RFD4, view a structure, or start the PD-L1 demo."""
        return {'ok':True}

    @mcp.tool(meta=APP, annotations=READ)
    def get_workspace() -> dict:
        """Read prepared plans and durable job records."""
        return service.overview()

    @mcp.tool(meta=APP, annotations=WRITE)
    def load_demo() -> dict:
        """Load the PD-L1 example supplied by the user's Studio deployment."""
        result=service.load_demo()
        return service.viewer_payload(result)

    @mcp.tool(meta=APP, annotations=WRITE)
    def import_structure(cif: str) -> dict:
        """Load an annotated molecular CIF into Studio."""
        result=service.import_cif(cif)
        return service.viewer_payload(result)

    @mcp.tool(meta=APP, annotations=WRITE)
    def open_result(job_id: str) -> dict:
        """Retrieve a completed result and open it for 3D inspection."""
        service.collect(job_id)
        result=service.open_result(job_id)
        return service.viewer_payload(result)
    @mcp.tool(meta=APP, annotations=WRITE)
    def open_run_structure(job_id: str, index: int | None=None) -> dict:
        """Open the saved input (no index) or a numbered generated design in Studio."""
        return service.open_run_structure(job_id,index)

    @mcp.tool(meta=APP, annotations=WRITE)
    def list_results(job_id: str) -> dict:
        """Retrieve and enumerate completed designs without running inference."""
        return service.results(job_id)

    @mcp.tool(meta=APP, annotations=WRITE)
    def download_results(job_id: str) -> dict:
        """Return a bounded ZIP of generated CIFs and the saved input."""
        return service.download_results(job_id)

    @mcp.tool(meta=APP, annotations=READ)
    def resolve_selection(session_id: str, atom_indices: list[int], scope: str='residue') -> dict:
        """Expand picked atoms using Studio's canonical residue/chain interpretation."""
        return service.resolve_selection(session_id, atom_indices, scope)

    @mcp.tool(meta=APP, annotations=WRITE)
    def set_condition(session_id: str, atom_indices: list[int], condition: str, enabled: bool, expected_revision: int) -> dict:
        """Update selected atom conditions only at the displayed document revision."""
        return service.set_condition(session_id, atom_indices, condition, enabled, expected_revision)

else:

    @mcp.tool(annotations=WRITE)
    def annotate_rfd4_structure(session_id: str, expression: str, condition: str) -> dict:
        """Apply a confirmed molecular selection through Studio's shared annotation provider. Image notes alone are not conditions."""
        return service.annotate(session_id,expression,condition)

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=READ)
def check_rfd4_job(job_id: str) -> dict:
    """Inspect a job, never resubmit an ambiguous run."""
    return service.public_job(service.status(job_id))

if __name__=='__main__':
    mcp.run(transport='stdio')
