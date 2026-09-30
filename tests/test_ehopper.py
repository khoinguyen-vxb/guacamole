"""Hopper setup checks; model calls are never made."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from examples.ehopper import ehopper
from guacamole import ContextSpec, Project


class EhopperTests(unittest.IsolatedAsyncioTestCase):
    async def test_launcher_enables_live_web_research(self):
        with (
            patch.object(ehopper.shutil, "which", return_value="/usr/bin/codex"),
            patch.object(ehopper.importlib.util, "find_spec", return_value=True),
            patch.object(
                ehopper, "Project", side_effect=RuntimeError("startup reached")
            ) as project,
            self.assertRaisesRegex(RuntimeError, "startup reached"),
        ):
            await ehopper.main()
        self.assertTrue(project.call_args.kwargs["reasoning"].web_search)

    def test_inventory_and_tool_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Project(root / "state", sandbox=root / "outputs") as project:
                ehopper.register_tools(project)
                request = ehopper.project_request(project, ContextSpec())
                self.assertIn(ehopper.DOCUMENTS / "brief.md", request.documents)
                self.assertIn(
                    ehopper.FREECAD_MCP / "docs/execution.md", request.documents
                )
                self.assertIn("5 minutes", request.description)
                self.assertIn("below 500", request.description)
                self.assertNotIn("Kookaburra", request.description)
                self.assertIn("6dof_hopper", ehopper.tool_paths())
                self.assertIn("freecad-mcp", ehopper.tool_paths())
                inventory = (project.sandbox / "context/inventory.md").read_text()
                self.assertIn("freecad.cmd", inventory)
                self.assertFalse(
                    project.tools.get("freecad_status@1").definition.requires_plan
                )
                self.assertTrue(
                    project.tools.get("freecad_run@1").definition.requires_plan
                )

    async def test_cad_outputs_errors_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Project(root / "state", sandbox=root / "outputs") as project:
                ehopper.register_tools(project)
                (project.sandbox / "cad.py").write_text("print('saved CAD script')")
                (project.sandbox / "model.FCStd").write_text("test export")
                tool = project.tools.get("freecad_run@1")
                call = AsyncMock(
                    return_value="Headless FreeCAD script finished (exit 0)."
                )
                with patch.object(ehopper, "_freecad_call", call):
                    result = await project.call(
                        tool,
                        {"script": "cad.py", "outputs": ["model.FCStd", "absent.step"]},
                    )
                    self.assertEqual(len(result.files), 1)
                    self.assertEqual(len(result.missing_outputs), 1)
                    self.assertTrue(Path(result.log.path).is_file())
                    self.assertEqual(call.call_args.args[0], "execute_code_headless")
                    self.assertIn("saved CAD script", call.call_args.args[1]["code"])
                    call.return_value = "Failed to run headless code: backend absent"
                    with self.assertRaisesRegex(
                        RuntimeError, "FreeCAD execution failed"
                    ):
                        await project.call(tool, {"script": "cad.py"})
                    call.return_value = "Code executed successfully: GUI fixture"
                    await project.call(tool, {"script": "cad.py", "headless": False})
                    self.assertEqual(call.call_args.args[0], "execute_code")
                    self.assertFalse(call.call_args.args[1]["include_screenshot"])
                    call.reset_mock()
                    for arguments in (
                        {"script": "../outside.py"},
                        {"script": "cad.py", "outputs": ["../outside.FCStd"]},
                    ):
                        with self.assertRaises(ValueError):
                            await project.call(tool, arguments)
                    call.assert_not_awaited()

    @unittest.skipUnless(os.environ.get("EHOPPER_FREECAD_SMOKE") == "1", "opt-in CAD")
    async def test_real_freecad_mcp_export(self):
        # Snap sees the user's home tree, but has a private /tmp.
        with (
            tempfile.TemporaryDirectory(dir=ehopper.ROOT) as directory,
            Project(Path(directory), sandbox=ehopper.SANDBOX / "setup") as project,
        ):
            ehopper.register_tools(project)
            script = project.output_path(Path("check_freecad.py"))
            script.write_text(
                "import FreeCAD as App, Part, json\n"
                "doc = App.newDocument('SetupCheck')\n"
                "obj = doc.addObject('Part::Box', 'CheckSolid')\n"
                "obj.Length, obj.Width, obj.Height = 10, 20, 30\n"
                "doc.recompute()\n"
                "assert obj.Shape.isValid() and len(obj.Shape.Solids) == 1\n"
                "assert abs(obj.Shape.Volume - 6000) < 1e-6\n"
                "doc.saveAs('setup-test.FCStd')\n"
                "Part.export([obj], 'setup-test.step')\n"
                "App.closeDocument(doc.Name)\n"
                "saved = App.openDocument('setup-test.FCStd')\n"
                "assert abs(saved.CheckSolid.Shape.Volume - 6000) < 1e-6\n"
                "shape = Part.Shape()\n"
                "shape.read('setup-test.step')\n"
                "assert shape.isValid() and len(shape.Solids) == 1\n"
                "assert abs(shape.Volume - 6000) < 1e-6\n"
                "with open('verification.json', 'w') as stream:\n"
                "    json.dump({'outcome': 'pass', 'volume_mm3': shape.Volume,\n"
                "               'solid_count': len(shape.Solids),\n"
                "               'freecad_version': App.Version()}, stream)\n",
                encoding="utf-8",
            )
            result = await project.call(
                project.tools.get("freecad_run@1"),
                {
                    "script": "check_freecad.py",
                    "outputs": [
                        "setup-test.FCStd",
                        "setup-test.step",
                        "verification.json",
                    ],
                    "timeout_s": 60.0,
                },
            )
            self.assertEqual(result.missing_outputs, ())
            self.assertEqual(len(result.files), 3)
            checks = json.loads((project.sandbox / "verification.json").read_text())
            self.assertEqual(checks["outcome"], "pass")
            self.assertAlmostEqual(checks["volume_mm3"], 6000)


if __name__ == "__main__":
    unittest.main()
