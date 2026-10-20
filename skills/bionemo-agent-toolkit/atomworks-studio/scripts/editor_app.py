"""Launch the pinned upstream editor with explicit, isolated host compatibility."""
import argparse
import os
from editor_identity import store_identity
from editor_compat import concatenate_with_classifications, verify_compatibility_sources

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
