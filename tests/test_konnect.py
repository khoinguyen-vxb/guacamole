"""Konnect KiCad tools; the Konnect binary is never run."""

import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from guacamole import Project
from guacamole.integrations import konnect

CALL = "guacamole.integrations.konnect.call"
READERS = (
    "konnect_status",
    "kicad_project_info",
    "kicad_erc",
    "kicad_drc",
    "kicad_design_review",
    "kicad_netlist_summary",
    "jlcpcb_search",
)
WRITERS = ("kicad_export_schematic_pdf", "kicad_export_manufacturing")


def text(value: str, error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=value)], is_error=error
    )


class KonnectTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.binary = root / "konnect"
        self.project = Project(root / "state", sandbox=root / "outputs")
        konnect.register_konnect_tools(self.project, self.binary, root / "konnect.toml")
        (self.project.sandbox / "board").mkdir()
        for name in ("board.kicad_pro", "board.kicad_sch", "board.kicad_pcb"):
            (self.project.sandbox / "board" / name).write_text("(fixture)")

    def tearDown(self):
        self.project.close()
        self.directory.cleanup()

    def tool(self, name: str):
        return self.project.tools.get(f"{name}@1")

    def test_registration_and_gates(self):
        for name in READERS:
            definition = self.tool(name).definition
            self.assertFalse(definition.requires_plan, name)
            self.assertTrue(definition.retry_safe, name)
            self.assertTrue(definition.show_errors, name)
        for name in WRITERS:
            definition = self.tool(name).definition
            self.assertTrue(definition.requires_plan, name)
            self.assertFalse(definition.retry_safe, name)
        self.assertIn("kicad-cli", self.tool("konnect_status").definition.description)
        self.assertEqual(
            {d.grant.name for d in self.project.tools.definitions()},
            set(READERS) | set(WRITERS),
        )

    def test_arguments_are_validated_before_konnect_runs(self):
        cases = (
            ("kicad_erc", {"schematic": "board/board.kicad_sch", "severity": "fatal"}),
            ("kicad_drc", {"board": "board/board.kicad_pcb", "limit": 0}),
            ("jlcpcb_search", {"query": "10k", "limit": 101}),
            ("kicad_project_info", {"project_file": "x", "extra": 1}),
        )
        with patch(CALL, AsyncMock()) as call:
            for name, arguments in cases:
                with self.subTest(name), self.assertRaises(ValidationError):
                    self.project.submit(self.tool(name), arguments)
            call.assert_not_called()

    async def test_reader_calls_load_their_toolset_with_sandbox_paths(self):
        sandbox = self.project.sandbox.resolve()
        cases = (
            ("konnect_status", {}, None, "get_installation_info", {}),
            (
                "kicad_project_info",
                {"project_file": "board/board.kicad_pro"},
                "project",
                "get_project_info",
                {"path": str(sandbox / "board/board.kicad_pro")},
            ),
            (
                "kicad_erc",
                {"schematic": "board/board.kicad_sch", "severity": "error"},
                "sch_export",
                "run_erc",
                {
                    "schematic": str(sandbox / "board/board.kicad_sch"),
                    "severity": "error",
                },
            ),
            (
                "kicad_drc",
                {"board": "board/board.kicad_pcb"},
                "verification",
                "run_drc",
                {
                    "board": str(sandbox / "board/board.kicad_pcb"),
                    "severity": "warning",
                    "limit": 50,
                },
            ),
            (
                "kicad_design_review",
                {
                    "schematic": "board/board.kicad_sch",
                    "board": "board/board.kicad_pcb",
                },
                "design_review",
                "run_design_review",
                {
                    "schematic": str(sandbox / "board/board.kicad_sch"),
                    "board": str(sandbox / "board/board.kicad_pcb"),
                    "severity_filter": "warning",
                },
            ),
            (
                "kicad_netlist_summary",
                {"schematic": "board/board.kicad_sch"},
                "sch_export",
                "export_netlist_summary",
                {"schematic": str(sandbox / "board/board.kicad_sch")},
            ),
            (
                "jlcpcb_search",
                {"query": "100nF 0402", "basic_only": True},
                "integration",
                "search_jlcpcb_parts",
                {
                    "query": "100nF 0402",
                    "basic_only": True,
                    "in_stock": True,
                    "limit": 20,
                },
            ),
        )
        for name, arguments, toolset, target, expected in cases:
            with (
                self.subTest(name),
                patch(CALL, AsyncMock(return_value=('{"ok":true}', ()))) as call,
            ):
                result = await self.project.call(self.tool(name), arguments)
                self.assertEqual(result, '{"ok":true}')
                binary, config, *rest = call.call_args.args
                self.assertEqual(binary, self.binary.resolve())
                self.assertEqual(config.name, "konnect.toml")
                self.assertEqual(rest[:3], [toolset, target, expected])

    async def test_exports_return_only_files_they_wrote(self):
        out = self.project.sandbox / "fab"
        out.mkdir()
        (out / "stale.txt").write_text("from an earlier run")

        async def export(binary, config, toolset, name, arguments, timeout_s):
            if name == "export_schematic_pdf":
                Path(arguments["output"]).write_text("%PDF fixture")
            else:
                directory = Path(arguments["output_dir"])
                (directory / "gerbers").mkdir()
                (directory / "gerbers" / "board-F_Cu.gbr").write_text("G04 fixture*")
                (directory / "bom.csv").write_text("Reference,Value")
            return '{"exported":true}', ()

        with patch(CALL, AsyncMock(side_effect=export)) as call:
            pdf = await self.project.call(
                self.tool("kicad_export_schematic_pdf"),
                {"schematic": "board/board.kicad_sch", "output": "docs/schematic.pdf"},
            )
            self.assertEqual(
                call.call_args.args[2:4], ("sch_export", "export_schematic_pdf")
            )
            self.assertEqual([Path(f.path).name for f in pdf.files], ["schematic.pdf"])
            package = await self.project.call(
                self.tool("kicad_export_manufacturing"),
                {
                    "board": "board/board.kicad_pcb",
                    "schematic": "board/board.kicad_sch",
                    "output_dir": "fab",
                    "bom_fields": "Reference,Value,MPN",
                },
            )
        self.assertEqual(
            call.call_args.args[2:4], ("manufacturing", "export_manufacturing_package")
        )
        arguments = call.call_args.args[4]
        self.assertEqual(arguments["fab_house"], "jlcpcb")
        self.assertEqual(arguments["bom_fields"], "Reference,Value,MPN")
        self.assertEqual(
            sorted(Path(f.path).name for f in package.files),
            ["board-F_Cu.gbr", "bom.csv"],
        )
        self.assertEqual(package.reply, '{"exported":true}')

    async def test_konnect_errors_reach_the_agent(self):
        error = RuntimeError('{"error":{"kind":"invalid_argument"}}')
        with patch(CALL, AsyncMock(side_effect=error)), self.assertRaises(RuntimeError):
            await self.project.call(
                self.tool("kicad_drc"), {"board": "board/board.kicad_pcb"}
            )
        failed = self.project.activity.requests(status="failed")
        self.assertIn("invalid_argument", failed[-1].reason)

    async def test_paths_outside_the_sandbox_are_refused(self):
        with patch(CALL, AsyncMock()) as call:
            with self.assertRaises(ValueError):
                await self.project.call(
                    self.tool("kicad_erc"), {"schematic": "../../etc/board.kicad_sch"}
                )
            call.assert_not_called()


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def session(self, *results):
        session = MagicMock()
        session.call_tool = AsyncMock(side_effect=results)

        @asynccontextmanager
        async def opened(binary, config):
            yield session

        return session, patch("guacamole.integrations.konnect._session", opened)

    async def test_call_loads_the_toolset_then_calls_the_tool(self):
        session, opened = self.session(
            text('{"loaded":"verification"}'), text('{"ok":1}')
        )
        with opened:
            reply, images = await konnect.call(
                Path("konnect"), None, "verification", "run_drc", {"board": "b"}, 9.0
            )
        self.assertEqual((reply, images), ('{"ok":1}', ()))
        names = [c.args[:2] for c in session.call_tool.call_args_list]
        self.assertEqual(
            names,
            [("load_toolset", {"name": "verification"}), ("run_drc", {"board": "b"})],
        )

    async def test_meta_tools_skip_loading_and_errors_raise(self):
        session, opened = self.session(text('{"message":"no kicad-cli"}', error=True))
        with opened, self.assertRaisesRegex(RuntimeError, "no kicad-cli"):
            await konnect.call(
                Path("konnect"), None, None, "get_installation_info", {}, 9.0
            )
        self.assertEqual(session.call_tool.call_args.args[0], "get_installation_info")

    async def test_server_environment_excludes_secrets(self):
        captured = {}

        class Stop(Exception):
            pass

        def stdio(parameters, errlog):
            captured["parameters"] = parameters
            raise Stop

        environment = {"ANTHROPIC_API_KEY": "secret", "KICAD_API_SOCKET": "s"}
        with (
            patch.dict("os.environ", environment),
            patch("guacamole.integrations.konnect.stdio_client", stdio),
            self.assertRaises(Stop),
        ):
            async with konnect._session(Path("/bin/konnect"), Path("k.toml")):
                pass
        parameters = captured["parameters"]
        self.assertNotIn("ANTHROPIC_API_KEY", parameters.env)
        self.assertEqual(parameters.env["KICAD_API_SOCKET"], "s")
        self.assertEqual(parameters.args, ["--config", "k.toml"])


if __name__ == "__main__":
    unittest.main()
