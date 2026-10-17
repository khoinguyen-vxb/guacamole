import json
import os
import sys
import tempfile
import unittest
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

from guacamole import Project
from guacamole.tools.containers import Container, ContainerRunner, HostRunner, runner
from guacamole.tools.execution import CURRENT_REQUEST

IMAGE = "openfoam/openfoam12@sha256:" + "a" * 64


def fake_engine(root: Path, ps: str = "") -> Path:
    """An engine that logs each call; `run` sleeps when told to, `ps` lists ps."""
    path = root / "engine"
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, time\n"
        f"open({str(root / 'calls')!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"if sys.argv[1] == 'ps': print({ps!r})\n"
        "if sys.argv[1] == 'run' and 'sleep' in sys.argv: time.sleep(30)\n"
        "if sys.argv[1] == 'run' and 'fail' in sys.argv:\n"
        "    print('no such tool'); sys.exit(3)\n"
        "if sys.argv[1] == 'run': print('ran')\n"
    )
    path.chmod(0o755)
    return path


class ContainerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.project = Project(self.root / "state", sandbox=self.root / "outputs")
        self.engine = fake_engine(self.root)

    def tearDown(self):
        self.project.close()
        self.directory.cleanup()

    def calls(self) -> list[list[str]]:
        lines = (self.root / "calls").read_text().splitlines()
        return [json.loads(line) for line in lines]

    def contained(self, **options) -> ContainerRunner:
        spec = Container(
            image=IMAGE, engine=str(self.engine), inputs=(self.inputs,), **options
        )
        return ContainerRunner(self.project, spec)

    def test_images_must_be_pinned_by_digest(self):
        for image in ("openfoam/openfoam12", "openfoam/openfoam12:latest"):
            with self.subTest(image), self.assertRaisesRegex(ValueError, "Pin image"):
                Container(image=image)
        Container(image=IMAGE)
        Container(image="sha256:" + "b" * 64)  # A local image ID

    def test_paths_translate_into_mounts_or_are_refused(self):
        runs = self.contained()
        sandbox = self.project.sandbox
        self.assertEqual(runs.path(sandbox), "/work")
        self.assertEqual(runs.path(sandbox / "cases/pitz"), "/work/cases/pitz")
        self.assertEqual(
            runs.path(self.inputs / "geometry.stl"), "/inputs/0/geometry.stl"
        )
        with self.assertRaisesRegex(ValueError, "outside every container mount"):
            runs.path(self.root / "state/project.sqlite3")
        with self.assertRaisesRegex(ValueError, "outside every container mount"):
            runs.path(sandbox / "../state")

    def test_launches_are_locked_down_and_labelled(self):
        environment = {"ANTHROPIC_API_KEY": "secret", "DOCKER_HOST": "unix:///d.sock"}
        token = CURRENT_REQUEST.set("request-1")
        try:
            with patch.dict("os.environ", environment):
                launch = self.contained(
                    env={"OMP_NUM_THREADS": "4"}, shm_size="1g"
                ).launch(["simpleFoam"], self.project.sandbox / "cases")
        finally:
            CURRENT_REQUEST.reset(token)
        argv = launch.argv
        self.assertEqual(argv[:3], [str(self.engine), "run", "--rm"])
        self.assertEqual(argv[-2:], [IMAGE, "simpleFoam"])
        pairs = set(pairwise(argv))
        for pair in (
            ("--network", "none"),
            ("--cap-drop", "ALL"),
            ("--security-opt", "no-new-privileges"),
            ("--workdir", "/work/cases"),
            ("--user", f"{os.getuid()}:{os.getgid()}"),
            ("--shm-size", "1g"),
            ("--label", f"guacamole.project={self.project.store.project_id}"),
            ("--label", "guacamole.request=request-1"),
            ("--env", "HOME=/tmp"),
            ("--env", "OMP_NUM_THREADS=4"),
            ("--mount", f"type=bind,source={self.project.sandbox},target=/work"),
            ("--mount", f"type=bind,source={self.inputs},target=/inputs/0,readonly"),
            ("--name", launch.container),
        ):
            self.assertIn(pair, pairs)
        # The engine client may reach its daemon; the container sees neither.
        self.assertEqual(launch.env["DOCKER_HOST"], "unix:///d.sock")
        self.assertNotIn("ANTHROPIC_API_KEY", launch.env)
        self.assertFalse(any("ANTHROPIC" in a or "DOCKER_HOST" in a for a in argv))
        networked = self.contained(network=True).launch(["x"], self.project.sandbox)
        self.assertNotIn("--network", networked.argv)
        self.assertNotIn("--userns", argv)

    def test_podman_keeps_the_host_user_and_skips_selinux_labels(self):
        podman = self.root / "bin/podman"
        podman.parent.mkdir()
        podman.symlink_to(self.engine)
        spec = Container(image=IMAGE, engine=str(podman))
        pairs = set(
            pairwise(
                ContainerRunner(self.project, spec)
                .launch(["x"], self.project.sandbox)
                .argv
            )
        )
        self.assertIn(("--userns", "keep-id"), pairs)
        self.assertIn(("--security-opt", "label=disable"), pairs)
        rootless = Container(image=IMAGE, engine=str(podman), user=None)
        argv = (
            ContainerRunner(self.project, rootless)
            .launch(["x"], self.project.sandbox)
            .argv
        )
        self.assertNotIn("--userns", argv)

    async def test_runs_log_output_and_a_timeout_kills_the_container(self):
        runs = self.contained()
        log = self.project.sandbox / "log.txt"
        code, timed_out = await runs.run(
            ["solver"], cwd=self.project.sandbox, log=log, timeout_s=30
        )
        self.assertEqual((code, timed_out, log.read_text()), (0, False, "ran\n"))
        code, timed_out = await runs.run(
            ["sleep"], cwd=self.project.sandbox, log=log, timeout_s=0.5
        )
        self.assertEqual((code, timed_out), (-1, True))
        started = next(c for c in self.calls() if c[0] == "run" and "sleep" in c)
        name = started[started.index("--name") + 1]
        self.assertIn(["kill", name], self.calls())

    async def test_capture_and_check_report_failures(self):
        runs = self.contained()
        self.assertEqual(
            await runs.capture(["fail"], cwd=self.project.sandbox, timeout_s=30),
            (3, "no such tool\n"),
        )
        with self.assertRaisesRegex(RuntimeError, "exited 3:\nno such tool"):
            runs.check(["fail"], cwd=self.project.sandbox)
        self.assertEqual(runs.check(["ok"], cwd=self.project.sandbox), "ran\n")

    def test_reaping_removes_this_projects_leftovers(self):
        self.engine = fake_engine(self.root, ps="c1\nc2")
        runner(self.project, Container(image=IMAGE, engine=str(self.engine)))
        label = f"label=guacamole.project={self.project.store.project_id}"
        self.assertEqual(
            self.calls(),
            [
                ["ps", "--all", "--quiet", "--filter", label],
                ["rm", "--force", "c1", "c2"],
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "not installed"):
            runner(self.project, Container(image=IMAGE, engine=str(self.root / "none")))

    def test_mcp_servers_run_interactively(self):
        server = self.contained().server(["konnect"], cwd=self.project.sandbox)
        self.assertEqual(server.command, str(self.engine))
        self.assertIn("--interactive", server.args)
        self.assertEqual(server.args[-2:], [IMAGE, "konnect"])

    def test_host_runs_get_only_the_minimal_environment(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "secret"}):
            launch = HostRunner({"KICAD_API_SOCKET": "s"}).launch(
                ["konnect"], self.root
            )
        self.assertNotIn("ANTHROPIC_API_KEY", launch.env)
        self.assertEqual(launch.env["KICAD_API_SOCKET"], "s")
        self.assertEqual(
            (launch.argv, launch.cwd, launch.container), (["konnect"], self.root, None)
        )
        self.assertEqual(HostRunner().path(self.root / "x"), str(self.root / "x"))
