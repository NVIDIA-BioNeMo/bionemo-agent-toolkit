"""Embedded Studio app and agent-only execution, following NGS Workbench boundaries."""
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
@mcp.resource(URI, name='rfd4-studio', title='AtomWorks Studio', mime_type='text/html;profile=mcp-app', meta={
    'ui':{'csp':{'connectDomains':[], 'resourceDomains':[], 'frameDomains':[]},'supportsFullscreen':True},
    'openai/ui':{'availableDisplayModes':['inline','fullscreen']},
    'openai/widgetCSP':{'connectDomains':[], 'resourceDomains':[], 'frameDomains':[]},
    'openai/widgetSupportsFullscreen':True,
    'openai/widgetAccessible':True,
})
def panel():
    return (Path(__file__).parents[1]/'assets/studio.html').read_text()

if mode == 'app':
    @mcp.tool(title='Open AtomWorks Studio in chat', meta={'ui/resourceUri':URI,'openai/outputTemplate':URI,'openai/widgetAccessible':True,'ui':{'resourceUri':URI,'visibility':['app','model'],'supportsFullscreen':True}}, annotations=READ)
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
    def prepare_design(session_id: str, note: str='', samples: int=1, seed: int=42, image_base64: str | None=None) -> dict:
        """Freeze and validate the editor state for review; never starts compute."""
        return service.prepare(session_id,note,samples,seed,image_base64)

    @mcp.tool(meta=APP, annotations=WRITE)
    def open_result(job_id: str) -> dict:
        """Retrieve a completed result and open it for 3D inspection."""
        service.collect(job_id)
        result=service.open_result(job_id)
        return service.viewer_payload(result)
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
    def prepare_rfd4_design(session_id: str, note: str='', samples: int=1, seed: int=42) -> dict:
        """Export an immutable annotated structure and checksum-bound compute plan."""
        return service.prepare(session_id,note,samples,seed)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=True))
    def execute_rfd4_plan(plan_id: str, plan_checksum: str) -> dict:
        """Run the reviewed plan on its exact Brev target. Requires host approval; costs GPU time. Reuse the same plan ID on retries."""
        result=service.execute(plan_id,plan_checksum)
        return {k:v for k,v in result.items() if k != 'target'}

    @mcp.tool(annotations=WRITE)
    def annotate_rfd4_structure(session_id: str, expression: str, condition: str) -> dict:
        """Apply a confirmed molecular selection through Studio's shared annotation provider. Image notes alone are not conditions."""
        return service.annotate(session_id,expression,condition)

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=READ)
def check_rfd4_job(job_id: str) -> dict:
    """Inspect a job, never resubmit an ambiguous run."""
    return {k:v for k,v in service.status(job_id).items() if k != 'target'}

if __name__=='__main__':
    mcp.run(transport='stdio')
