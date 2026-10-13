"""Exercise the actual MCP stdio boundary without compute or network."""
import os
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
                    if mode=='app':
                        result=await session.call_tool('get_workspace',{})
                        self.assertFalse(result.isError)
                        if (server.parents[1]/'assets/studio-upstream.html').exists():
                            resource=await session.read_resource('ui://bionemo-rfd4/studio.html')
                            self.assertIn('ui/initialize',resource.contents[0].text)
                        self.assertNotIn('register_rfd4_compute',names)
                        self.assertIn('studio_request',names)
                        for tool in tools:
                            self.assertEqual(tool.meta['ui']['visibility'],['app','model'] if tool.name=='open_rfd4_studio' else ['app'])
                            self.assertNotIn('openai/ui', tool.meta)
                            self.assertNotIn('com.openai', tool.meta)
                            if tool.name=='open_rfd4_studio':
                                self.assertEqual(tool.meta['openai/outputTemplate'],'ui://bionemo-rfd4/studio.html')
                                self.assertEqual(tool.meta['ui/resourceUri'],'ui://bionemo-rfd4/studio.html')
                    else:
                        execute=next(t for t in tools if t.name=='execute_rfd4_plan')
                        self.assertEqual(execute.meta['ui']['visibility'],['model'])
    async def test_app(self): await self.check_mode('app')
    async def test_agent(self): await self.check_mode('agent')

if __name__=='__main__': unittest.main()
