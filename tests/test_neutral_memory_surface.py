"""Public MCP compatibility checks without storage, embedding or model calls."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from lab_neutral_surface import SURFACE, install_neutral_surface
from ombrebrain.policy.surfacing import SurfaceMode, SurfacePolicyVM


class NeutralMemorySurfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_preserves_arguments_results_errors_and_legacy_calls(self):
        server = FastMCP("test")
        calls = []

        @server.tool()
        async def hold(content: str, importance: int = 5) -> str:
            calls.append((content, importance))
            return content

        original = (await server.list_tools())[0]
        install_neutral_surface(server)
        async with create_connected_server_and_client_session(server) as session:
            listing = await session.list_tools()
            tool = listing.tools[0]
            self.assertEqual(tool.name, "memory_add")
            old_schema, new_schema = dict(original.inputSchema), dict(tool.inputSchema)
            old_schema.pop("title", None)
            new_schema.pop("title", None)
            self.assertEqual(old_schema, new_schema)
            text = "Ombre breath I: these words belong to the stored quotation."
            for name in ("memory_add", "hold"):
                result = await session.call_tool(name, {"content": text, "importance": 8})
                self.assertFalse(result.isError)
                self.assertEqual(result.content[0].text, text)
            invalid = await session.call_tool("memory_add", {"importance": []})
            self.assertTrue(invalid.isError)
            self.assertEqual(calls, [(text, 8), (text, 8)])

    async def test_dynamic_profiles_appear_and_disappear_after_installation(self):
        server = FastMCP("test")
        install_neutral_surface(server)
        async def profile(content: str = "") -> str:
            return content
        for name in ("You", "Them"):
            server.add_tool(profile, name=name)
            self.assertIn(SURFACE[name][0], [t.name for t in await server.list_tools()])
            server.remove_tool(name)
            self.assertNotIn(SURFACE[name][0], [t.name for t in await server.list_tools()])
        self.assertNotIn("I", SURFACE)

    def test_identity_exclusion_does_not_filter_ordinary_story_records(self):
        policy = SurfacePolicyVM.default()
        for mode in SurfaceMode:
            for metadata in ({"type": "i"}, {"type": "self"}, {"type": "dynamic", "i_stage": "candidate"}, {"tags": ["__i_candidate__"]}):
                self.assertFalse(policy.evaluate_bucket({"id": "legacy-i", "metadata": metadata}, mode).allowed)
            self.assertTrue(policy.evaluate_bucket({"id": "event", "metadata": {"type": "dynamic"}}, mode).allowed)


if __name__ == "__main__":
    unittest.main()
