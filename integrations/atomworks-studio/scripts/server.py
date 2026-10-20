"""Embedded Studio app and agent-only execution, with self-contained BioNeMo compute management."""
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
    asset=Path(__file__).parents[1]/'assets/studio-upstream.html'
    if not asset.exists(): raise RuntimeError('Build the pinned upstream Studio frontend first; see the adapter README.')
    return asset.read_text()

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=READ)
def get_compute_status(session_id: str | None=None) -> dict:
    """Read registered target and timestamped readiness evidence. Does not provision or probe."""
    return service.compute_status(session_id)

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=READ)
def check_compute(session_id: str | None=None) -> dict:
    """Probe existing target GPU, pinned runtime, registered weights and Studio; never provision."""
    return service.check_compute(session_id)

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=READ)
def list_registered_compute() -> dict:
    """List saved BioNeMo compute targets; no external registry or provisioning."""
    return service.available_compute()

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=READ)
def inspect_compute_target(target_id: str) -> dict:
    """Check the connection to a saved BioNeMo target, separately from model readiness."""
    return service.inspect_compute_target(target_id)

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=READ)
def get_compute_capabilities() -> dict:
    """Read protocol, schema and executor identity before mutating compute."""
    return service.capabilities()

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=WRITE)
def disconnect_compute(session_id: str, expected_revision: int) -> dict:
    """Disconnect only this session. Does not stop machines or jobs or billing."""
    return service.disconnect_compute(session_id, expected_revision)

@mcp.tool(meta=APP if mode == 'app' else {}, annotations=WRITE)
def select_compute(target_id: str, session_id: str, expected_revision: int) -> dict:
    """Explicitly select a saved machine at the inspected session revision; never starts it."""
    return service.register_registry_compute(target_id, session_id=session_id, expected_revision=expected_revision)

@mcp.tool(meta={'ui':{'visibility':['app','model']}} if mode == 'app' else {}, annotations=READ)
def get_rfd4_export(export_id: str) -> dict:
    """Verify a saved export and return its local path. Share it as a Markdown file link; no compute is contacted."""
    from local_exports import get
    return get(service.root,export_id)

if mode == 'app':
    @mcp.tool(meta=APP, annotations=WRITE)
    def save_rfd4_export(filename: str, mime_type: str, text: str | None=None, base64_data: str | None=None) -> dict:
        """Save the exact clicked CIF/ZIP locally for export through chat; never starts compute."""
        from local_exports import save
        return save(service.root,filename,mime_type,text,base64_data)

    @mcp.tool(meta=APP, annotations=WRITE)
    def begin_compute_setup(session_id: str, expected_revision: int, target_id: str | None=None) -> dict:
        """Create or resume a setup conversation reference. Does not provision or connect."""
        return service.begin_setup(session_id, target_id, expected_revision)
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
        from studio_bridge import request
        return request(service,method,path,body,form)

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
    def prepare_design(session_id: str, note: str='', samples: int=1, seed: int=42, image_base64: str | None=None, generation: dict | None=None) -> dict:
        """Freeze and validate the editor state for review; never starts compute."""
        return service.prepare(session_id,note,samples,seed,image_base64,generation)

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
    def prepare_executor_claim(operation_id: str, machine_id: str) -> dict:
        """Review initial single-controller machine ownership. Verifies access and identity but does not claim, install, start or run anything. The reviewed claim requires administrator permission and persists after disconnect; ownership transfer is unsupported."""
        return service.prepare_executor_claim(operation_id,machine_id)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def execute_executor_claim(operation_id: str, review_checksum: str) -> dict:
        """After approval, establish exactly the reviewed protected machine ownership using sudo noninteractively. No credentials are requested in chat; no power change or inference. Retrying a dispatched request only inspects its outcome."""
        return service.execute_executor_claim(operation_id,review_checksum)

    @mcp.tool(annotations=READ)
    def reconcile_executor_claim(operation_id: str) -> dict:
        """Read the protected owner and publication marker after an uncertain claim. Never repeats the privileged action or replaces an owner."""
        return service.reconcile_executor_claim(operation_id)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def confirm_executor_claim(operation_id: str, review_checksum: str) -> dict:
        """After explicit approval, finish durability of an already-present matching reviewed owner. Uses sudo; cannot create a missing owner or replace another controller. No runtime, power or inference effects."""
        return service.confirm_executor_claim(operation_id,review_checksum)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=WRITE)
    def recover_compute_access(operation_id: str) -> dict:
        """After a refresh controller crash, verify its process lease is free and close the unaccepted access attempt. Never reruns refresh or enrolls host keys. A new attempt requires a new explicitly approved operation."""
        return service.recover_compute_access(operation_id)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def refresh_compute_access(operation_id: str, machine_id: str) -> dict:
        """Explicitly refresh local Brev SSH/key/helper configuration for a saved running machine. Verifies organization, immutable instance and physical identity using existing trusted host keys. Never enrolls keys, starts a machine, installs RFD4 or submits inference. Unknown host keys require independent verification outside this tool."""
        return service.refresh_compute_access(operation_id,machine_id)

    @mcp.tool(annotations=READ)
    def list_compute_creation_options(organization_id: str) -> dict:
        """List available single-A100-80GB machine specifications and price estimates in an explicit Brev organization. Does not provision."""
        return service.list_compute_creation_options(organization_id)

    @mcp.tool(annotations=WRITE)
    def prepare_compute_creation(operation_id: str, organization_id: str, instance_type: str) -> dict:
        """Review one billable Brev A100 80 GB instance in an explicit organization. Does not create, install or run anything."""
        return service.prepare_compute_creation(operation_id, organization_id, instance_type)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def execute_compute_creation(operation_id: str, review_checksum: str) -> dict:
        """Create exactly the reviewed billable machine after approval. Retry only reconciles the original request; no automatic setup or inference."""
        return service.execute_compute_creation(operation_id, review_checksum)

    @mcp.tool(annotations=READ)
    def reconcile_compute_creation(operation_id: str) -> dict:
        """Observe a previously dispatched creation without requesting another machine."""
        return service.reconcile_compute_creation(operation_id)

    @mcp.tool(annotations=WRITE)
    def prepare_runtime_setup(operation_id: str, machine_id: str) -> dict:
        """Review setup on the selected machine. If package archives are missing, returns a download-only prepare_archives phase with bytes and effects. After that phase completes, obtain a new setup operation and installation review. Binds exact helper hashes and target; this tool neither downloads nor installs."""
        return service.prepare_runtime_setup(operation_id, machine_id)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def execute_runtime_setup(operation_id: str, review_checksum: str) -> dict:
        """After approval, execute exactly the reviewed setup phase once. prepare_archives only downloads and verifies packages; it never installs or establishes readiness. A subsequent installation requires a new review. Runtime setup fetches pinned source, installs checkpoints and verifies inference readiness."""
        return service.execute_runtime_setup(operation_id, review_checksum)

    @mcp.tool(annotations=READ)
    def reconcile_runtime_setup(operation_id: str) -> dict:
        """Inspect the original setup process without launching another installer."""
        return service.reconcile_runtime_setup(operation_id)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=WRITE)
    def recover_runtime_setup(operation_id: str) -> dict:
        """Resolve an unknown setup by checking remote leases and fencing an orphaned dispatch. Never kills a process, repeats installation, or rolls back prior effects. Busy or unreachable machines retain their reservation. A new attempt requires a new review."""
        return service.recover_runtime_setup(operation_id)

    @mcp.tool(annotations=WRITE)
    def prepare_compute_stop(operation_id: str, machine_id: str, dedicated_machine: bool=False) -> dict:
        """Review stopping a dedicated single-user Brev machine. Requires user confirmation of dedicated ownership; no power change."""
        return service.prepare_stop(operation_id, machine_id, dedicated_machine)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
    def execute_compute_stop(operation_id: str, review_checksum: str) -> dict:
        """Stop exactly the reviewed dedicated machine after approval and fresh activity checks. Unknown activity blocks stop. No SSH shutdown fallback."""
        return service.execute_stop(operation_id, review_checksum)

    @mcp.tool(annotations=WRITE)
    def prepare_compute_start(operation_id: str, machine_id: str) -> dict:
        """Review starting one saved Brev instance. No provisioning or power change."""
        return service.prepare_start(operation_id, machine_id)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def execute_compute_start(operation_id: str, review_checksum: str) -> dict:
        """Start exactly the reviewed instance after user/host approval; resumes billing, never runs a design. App messages alone are not authorization. Retry the same operation to reconcile."""
        return service.execute_start(operation_id, review_checksum)

    @mcp.tool(annotations=READ)
    def reconcile_compute_power(operation_id: str) -> dict:
        """Observe a pending power operation without repeating it."""
        return service.reconcile_power(operation_id)

    @mcp.tool(annotations=READ)
    def get_compute_operation(operation_id: str) -> dict:
        """Inspect the authoritative action and session. App messages are not lifecycle authorization."""
        return service.compute_operation(operation_id)

    @mcp.tool(annotations=WRITE)
    def cancel_compute_operation(operation_id: str) -> dict:
        """Cancel future steps, retaining any unknown dispatched outcome for reconciliation."""
        return service.cancel_compute_operation(operation_id)

    @mcp.tool(annotations=WRITE)
    def register_rfd4_compute(kind: str, name: str, runtime_root: str, studio_url: str, expected_revision: int, organization_id: str | None=None, ssh_host: str='', instance_id: str='', weight_paths: list[str] | None=None, session_id: str | None=None) -> dict:
        """Register a user-selected existing local, SSH, or Brev target. This does not provision or install. Use existing setup and Brev CLI skills first; tunnel Studio to loopback. Then call check_compute. Weight paths are actual checkpoint files. Never invent readiness."""
        return service.register_compute(kind,name,runtime_root,studio_url,ssh_host,instance_id,weight_paths,session_id,organization_id=organization_id,expected_revision=expected_revision)

    @mcp.tool(annotations=WRITE)
    def use_registered_compute(target_id: str, expected_revision: int, runtime_root: str | None=None, studio_url: str | None=None, weight_paths: list[str] | None=None, session_id: str | None=None) -> dict:
        """Select an existing BioNeMo compute target for this Studio session. Saved runtime/checkpoint paths are reused. No provisioning or installation. Check compute separately."""
        return service.register_registry_compute(target_id,runtime_root,studio_url,weight_paths,session_id,expected_revision)

    @mcp.tool(annotations=WRITE)
    def prepare_rfd4_design(session_id: str, note: str='', samples: int=1, seed: int=42, generation: dict | None=None) -> dict:
        """Export an immutable annotated structure and checksum-bound compute plan."""
        return service.prepare(session_id,note,samples,seed,generation=generation)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=True))
    def execute_rfd4_plan(plan_id: str, plan_checksum: str) -> dict:
        """Run the reviewed plan on its exact Brev target. Requires host approval; costs GPU time. Reuse the same plan ID on retries."""
        result=service.execute(plan_id,plan_checksum)
        return service.public_job(result)

    @mcp.tool(meta={'ui':{'visibility':['model']}}, annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=True))
    def recover_queued_rfd4_job(job_id: str, accepted_plan_checksum: str) -> dict:
        """Explicitly continue an accepted queued job with its original review/checksum. May use GPU time. Never retries possibly dispatched work or creates another job. For submitted/unknown jobs use check_rfd4_job."""
        result=service.recover_queued_job(job_id,accepted_plan_checksum)
        return service.public_job(result)

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
