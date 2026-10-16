"""Hopper setup checks; model calls are never made."""

import base64
import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp.types import ImageContent

from examples.ehopper import ehopper
from guacamole import ContextSpec, Project


class EhopperTests(unittest.IsolatedAsyncioTestCase):
    def test_interject_targets_active_run_and_retries_with_same_id(self):
        with (
            patch("getpass.getpass", return_value="test-token"),
            patch("websockets.sync.client.connect") as connect,
            patch("builtins.print"),
        ):
            for _ in range(2):
                runpy.run_module("examples.ehopper.interject", run_name="__main__")
        messages = connect.return_value.__enter__.return_value.send.call_args_list
        first, retry = [json.loads(call.args[0]) for call in messages]
        self.assertNotIn("run_id", first["command"])
        self.assertTrue(first["command"]["keep_workers"])
        self.assertEqual(first, retry)

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

    def test_sysml_runtime_uses_repository_assets(self):
        library = Path("/tmp/sysml/stdlib")
        native = Path("/tmp/sysml/libsysmlv2_abi.so")

        def glob(pattern):
            return [library] if pattern.endswith("sysml/stdlib") else [native]

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(ehopper.Path, "glob", side_effect=glob),
        ):
            ehopper.configure_sysml_runtime()
            self.assertEqual(os.environ["GUACAMOLE_SYSML_LIBRARY"], str(library))
            self.assertEqual(os.environ["SYSMLV2_ABI"], str(native))

    async def test_inventory_and_tool_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Project(root / "state", sandbox=root / "outputs") as project:
                ehopper.register_tools(project)
                (project.sandbox / "sysml/model.sysml").parent.mkdir(parents=True)
                (project.sandbox / "sysml/model.sysml").write_text("package Model {}")
                request = ehopper.project_request(project, ContextSpec())
                self.assertIn(ehopper.DOCUMENTS / "brief.md", request.documents)
                self.assertEqual(
                    len([p for p in request.documents if p.suffix == ".jpg"]), 7
                )
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
                for name in ("freecad_status@1", "freecad_view@1"):
                    self.assertFalse(project.tools.get(name).definition.requires_plan)
                self.assertTrue(
                    project.tools.get("freecad_run@1").definition.requires_plan
                )
                listed = await project.call(
                    project.tools.get("list_files@1"), {"path": "sysml"}
                )
                self.assertEqual(listed, (str(project.sandbox / "sysml/model.sysml"),))
                self.assertEqual(
                    await project.call(
                        project.tools.get("read_text@1"),
                        {"path": "sysml/model.sysml"},
                    ),
                    "package Model {}",
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
                    return_value=("Headless FreeCAD script finished (exit 0).", ())
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
                    self.assertTrue(result.succeeded)
                    call.return_value = (
                        "Failed to run headless code: backend absent",
                        (),
                    )
                    failed = await project.call(tool, {"script": "cad.py"})
                    self.assertFalse(failed.succeeded)
                    self.assertIn("backend absent", failed.reply)
                    screenshot = ImageContent(
                        type="image",
                        data=base64.b64encode(b"fixture png").decode(),
                        mime_type="image/png",
                    )
                    call.return_value = (
                        "Code executed successfully: GUI fixture",
                        (screenshot,),
                    )
                    gui = await project.call(
                        tool, {"script": "cad.py", "headless": False}
                    )
                    self.assertEqual(call.call_args.args[0], "execute_code")
                    (view,) = gui.views
                    self.assertEqual(Path(view.path).read_bytes(), b"fixture png")
                    view_tool = project.tools.get("freecad_view@1")
                    call.return_value = ("", (screenshot,))
                    shown = await project.call(view_tool, {"view": "Front"})
                    self.assertEqual(
                        call.call_args.args[:2], ("get_view", {"view_name": "Front"})
                    )
                    self.assertTrue(shown.view.path.endswith(".png"))
                    call.return_value = ("Cannot get screenshot in this view", ())
                    blank = await project.call(view_tool, {})
                    self.assertEqual(
                        (blank.view, blank.reply),
                        (None, "Cannot get screenshot in this view"),
                    )
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
