"""Exercise the actual MCP stdio boundary without compute or network."""
import os
import json
from pathlib import Path
import sys
import tempfile
import unittest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class Protocol(unittest.IsolatedAsyncioTestCase):
    async def check_mode(self, mode, packaged=False):
        with tempfile.TemporaryDirectory() as root:
            repo=Path(__file__).resolve().parents[1]
            base='skills/bionemo-agent-toolkit/atomworks-studio' if packaged else 'integrations/atomworks-studio'
            server=repo/base/'scripts/server.py'
            params=StdioServerParameters(command=sys.executable,args=[str(server),mode],env={**os.environ,'RFD4_STUDIO_HOME':root})
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as session:
                    await session.initialize()
                    tools=(await session.list_tools()).tools
                    names={tool.name for tool in tools}
                    resources=(await session.list_resources()).resources
                    self.assertEqual(resources[0].meta['ui']['csp']['frameDomains'],[])
                    self.assertEqual('submit_design_request' in names,mode=='agent')
                    self.assertEqual('check_named_target' in names,mode=='agent')
                    self.assertIn('get_design_request', names)
                    self.assertIn('prepare_design_request', names)
                    for obsolete in ('execute_rfd4_plan', 'recover_queued_rfd4_job', 'refresh_selected_compute_access',
                                     'execute_compute_creation', 'execute_compute_stop', 'prepare_executor_claim', 'select_compute'):
                        self.assertNotIn(obsolete, names)
                    if mode=='app':
                        exported=await session.call_tool('save_rfd4_export',{'filename':'uat.cif','mime_type':'chemical/x-mmcif','text':'data_preserved\n'})
                        self.assertFalse(exported.isError)
                        saved=json.loads(exported.content[0].text)
                        retrieved=await session.call_tool('get_rfd4_export',{'export_id':saved['export_id']})
                        self.assertFalse(retrieved.isError)
                        file=Path(json.loads(retrieved.content[0].text)['path'])
                        self.assertTrue(file.is_relative_to(Path(root).resolve()))
                        self.assertEqual(file.read_text(),'data_preserved\n')
                        result=await session.call_tool('get_workspace',{})
                        self.assertFalse(result.isError)
                        if (server.parents[1]/'assets/studio-upstream.html').exists():
                            resource=await session.read_resource('ui://bionemo-rfd4/studio.html')
                            self.assertIn('ui/initialize',resource.contents[0].text)
                        self.assertNotIn('register_rfd4_compute',names)
                        self.assertIn('studio_request',names)
                        for tool in tools:
                            self.assertEqual(tool.meta['ui']['visibility'],['app','model'] if tool.name in ('open_rfd4_studio','get_rfd4_export') else ['app'])
                            self.assertNotIn('openai/ui', tool.meta)
                            self.assertNotIn('com.openai', tool.meta)
                            if tool.name=='open_rfd4_studio':
                                self.assertEqual(tool.meta['openai/outputTemplate'],'ui://bionemo-rfd4/studio.html')
                                self.assertEqual(tool.meta['ui/resourceUri'],'ui://bionemo-rfd4/studio.html')
                    else:
                        self.assertNotIn('save_rfd4_export',names)
                        self.assertIn('get_rfd4_export',names)
                        execute=next(t for t in tools if t.name=='submit_design_request')
                        self.assertFalse(execute.annotations.readOnlyHint)
                        self.assertTrue(execute.annotations.openWorldHint)
                        config=json.loads((repo/'skills/bionemo-agent-toolkit/.mcp.json').read_text())
                        agent=next(value for value in config['mcpServers'].values() if value.get('args')==['agent'])
                        self.assertEqual(agent['tools'], {'submit_design_request': {'approval_mode':'prompt'}})
    async def test_app(self): await self.check_mode('app')
    async def test_agent(self): await self.check_mode('agent')
    async def test_packaged_app(self): await self.check_mode('app', packaged=True)
    async def test_packaged_agent(self): await self.check_mode('agent', packaged=True)

if __name__=='__main__': unittest.main()
