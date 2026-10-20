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
    async def check_mode(self, mode):
        with tempfile.TemporaryDirectory() as root:
            server=Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts/server.py'
            params=StdioServerParameters(command=sys.executable,args=[str(server),mode],env={**os.environ,'RFD4_STUDIO_HOME':root})
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as session:
                    await session.initialize()
                    tools=(await session.list_tools()).tools
                    names={tool.name for tool in tools}
                    resources=(await session.list_resources()).resources
                    self.assertEqual(resources[0].meta['ui']['csp']['frameDomains'],[])
                    self.assertEqual('execute_rfd4_plan' in names,mode=='agent')
                    self.assertEqual('recover_queued_rfd4_job' in names,mode=='agent')
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
                        execute=next(t for t in tools if t.name=='execute_rfd4_plan')
                        self.assertEqual(execute.meta['ui']['visibility'],['model'])
                        recovery=next(t for t in tools if t.name=='recover_queued_rfd4_job')
                        self.assertEqual(recovery.meta['ui']['visibility'],['model'])
                        config=json.loads((server.parents[3]/'skills/bionemo-agent-toolkit/.mcp.json').read_text())
                        agent=next(value for value in config['mcpServers'].values() if 'execute_rfd4_plan' in value.get('tools',{}))
                        self.assertEqual(agent['tools']['recover_queued_rfd4_job']['approval_mode'],'prompt')
    async def test_app(self): await self.check_mode('app')
    async def test_agent(self): await self.check_mode('agent')

if __name__=='__main__': unittest.main()
