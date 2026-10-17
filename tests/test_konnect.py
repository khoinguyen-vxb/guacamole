"""Konnect KiCad tools; the Konnect binary is never run."""

import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp import StdioServerParameters
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from guacamole import Project
from guacamole.integrations import konnect
from guacamole.tools.containers import Container

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
                server, *rest = call.call_args.args
                self.assertEqual(server.command, str(self.binary.resolve()))
                self.assertEqual(server.args[0], "--config")
                self.assertTrue(server.args[1].endswith("konnect.toml"))
                self.assertEqual(rest[:3], [toolset, target, expected])

    async def test_exports_return_only_files_they_wrote(self):
        out = self.project.sandbox / "fab"
        out.mkdir()
        (out / "stale.txt").write_text("from an earlier run")

        async def export(server, toolset, name, arguments, timeout_s):
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
                call.call_args.args[1:3], ("sch_export", "export_schematic_pdf")
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
            call.call_args.args[1:3], ("manufacturing", "export_manufacturing_package")
        )
        arguments = call.call_args.args[3]
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


SERVER = StdioServerParameters(command="konnect")


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def session(self, *results):
        session = MagicMock()
        session.call_tool = AsyncMock(side_effect=results)

        @asynccontextmanager
        async def opened(server):
            yield session

        return session, patch("guacamole.integrations.konnect._session", opened)

    async def test_call_loads_the_toolset_then_calls_the_tool(self):
        session, opened = self.session(
            text('{"loaded":"verification"}'), text('{"ok":1}')
        )
        with opened:
            reply, images = await konnect.call(
                SERVER, "verification", "run_drc", {"board": "b"}, 9.0
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
            await konnect.call(SERVER, None, "get_installation_info", {}, 9.0)
        self.assertEqual(session.call_tool.call_args.args[0], "get_installation_info")


class ServerTests(unittest.IsolatedAsyncioTestCase):
    """How the server starts: on the host, or in a container."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.project = Project(self.root / "state", sandbox=self.root / "outputs")
        self.config = self.project.sandbox / "konnect.toml"
        self.config.write_text("")

    def tearDown(self):
        self.project.close()
        self.directory.cleanup()

    async def started(self, **options):
        """The server and arguments a kicad_erc call hands to Konnect."""
        konnect.register_konnect_tools(
            self.project, Path("/opt/konnect/bin/konnect"), self.config, **options
        )
        with patch(CALL, AsyncMock(return_value=("{}", ()))) as call:
            await self.project.call(
                self.project.tools.get("kicad_erc@1"),
                {"schematic": "board/board.kicad_sch"},
            )
        return call.call_args.args[0], call.call_args.args[3]

    async def test_host_server_environment_excludes_secrets(self):
        environment = {"ANTHROPIC_API_KEY": "secret", "KICAD_API_SOCKET": "s"}
        with patch.dict("os.environ", environment):
            server, _ = await self.started()
        self.assertNotIn("ANTHROPIC_API_KEY", server.env)
        self.assertEqual(server.env["KICAD_API_SOCKET"], "s")

    async def test_a_container_server_sees_only_container_paths(self):
        engine = self.root / "engine"
        engine.write_text(f'#!/bin/sh\necho "$*" >> {self.root}/engine.log\n')
        engine.chmod(0o755)
        image = "konnect@sha256:" + "0" * 64
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret"}):
            server, arguments = await self.started(
                container=Container(image=image, engine=str(engine))
            )
        self.assertEqual(server.command, str(engine))
        self.assertIn("--interactive", server.args)
        after = server.args[server.args.index(image) + 1 :]
        self.assertEqual(
            after, ["/opt/konnect/bin/konnect", "--config", "/work/konnect.toml"]
        )
        self.assertEqual(arguments["schematic"], "/work/board/board.kicad_sch")
        self.assertNotIn("ANTHROPIC_API_KEY", server.env)
        reaped = (self.root / "engine.log").read_text()
        self.assertIn(
            f"label=guacamole.project={self.project.store.project_id}", reaped
        )


if __name__ == "__main__":
    unittest.main()
