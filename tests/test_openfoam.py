import os
import tempfile
import unittest
from pathlib import Path

from guacamole import Project
from guacamole.integrations.openfoam import (
    environment,
    parse_mesh,
    parse_residuals,
    parse_table,
    register_openfoam_tools,
)

TUTORIAL = "incompressible/simpleFoam/pitzDaily"
SOLVER_LOG = """Create time

Time = 1s

smoothSolver:  Solving for Ux, Initial residual = 1, Final residual = 0.05, No Iterations 1
smoothSolver:  Solving for Uy, Initial residual = 1, Final residual = 0.03, No Iterations 2
GAMG:  Solving for p, Initial residual = 1, Final residual = 0.06, No Iterations 17
time step continuity errors : sum local = 1.19733, global = 0.179883, cumulative = 0.179883
ExecutionTime = 0.06 s  ClockTime = 0 s

Time = 2s

smoothSolver:  Solving for Ux, Initial residual = 0.01, Final residual = 0.0005, No Iterations 1
smoothSolver:  Solving for Uy, Initial residual = 0.02, Final residual = 0.001, No Iterations 2
GAMG:  Solving for p, Initial residual = 0.05, Final residual = 0.004, No Iterations 12
GAMG:  Solving for p, Initial residual = 0.9, Final residual = 0.004, No Iterations 12
time step continuity errors : sum local = 0.0012, global = 1e-05, cumulative = 0.18

Time = 3s

smoothSolver:  Solving for Ux, Initial residual = 0.0005, Final residual = 1e-05, No Iterations 1
smoothSolver:  Solving for Uy, Initial residual = 0.0004, Final residual = 1e-05, No Iterations 1
GAMG:  Solving for p, Initial residual = 0.0008, Final residual = 5e-05, No Iterations 9
time step continuity errors : sum local = 2.5e-06, global = 1e-08, cumulative = 0.18

End

"""
MESH_LOG = """Mesh stats
    points:           25012
    cells:            12225

Checking geometry...
    Mesh non-orthogonality Max: 65.3 average: 4.2
 ***Max skewness = 4.8, 1 highly skew faces

Failed 1 mesh checks.

End
"""
FATAL_LOG = """Create time


--> FOAM FATAL IO ERROR:
keyword div(phi,U) is undefined in dictionary "system/fvSchemes/divSchemes"

file: system/fvSchemes/divSchemes from line 25 to line 30.

FOAM exiting

"""


def script(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


class ParserTests(unittest.TestCase):
    def test_residuals_take_each_fields_first_solve_per_time_step(self):
        report = parse_residuals(SOLVER_LOG, 1e-3)
        self.assertEqual(
            (report.verdict, report.steps, report.last_time), ("converged", 3, "3")
        )
        p = next(f for f in report.fields if f.field == "p")
        self.assertEqual((p.first, p.last, p.maximum, p.steps), (1.0, 0.0008, 1.0, 3))
        self.assertTrue(report.end_reached)
        self.assertEqual(report.continuity, 2.5e-06)
        self.assertEqual(parse_residuals(SOLVER_LOG, 1e-4).verdict, "not_converged")

    def test_esi_logs_and_divergence(self):
        esi = SOLVER_LOG.replace("Time = 3s", "Time = 3").replace(
            "smoothSolver", "DILUPBiCGStab"
        )
        self.assertEqual(parse_residuals(esi, 1e-3).last_time, "3")
        diverged = parse_residuals(SOLVER_LOG.replace("= 0.0008,", "= nan,"), 1e-3)
        p = next(f for f in diverged.fields if f.field == "p")
        self.assertEqual((diverged.verdict, p.last, p.nonfinite), ("diverged", None, 1))
        self.assertIsNone(parse_residuals("blockMesh output\nEnd\n", 1e-4))

    def test_mesh_check_and_tables(self):
        mesh = parse_mesh(MESH_LOG)
        self.assertEqual(
            (
                mesh.ok,
                mesh.failed_checks,
                mesh.cells,
                mesh.max_non_orthogonality,
                mesh.max_skewness,
            ),
            (False, 1, 12225, 65.3, 4.8),
        )
        self.assertIsNone(parse_mesh(SOLVER_LOG))
        table = "# Forces\n# Time  total_x  total_y  total_z\n1 (1 2 3)\n2 (1.5 2.5 nan)\n3 (2 3 4)\n"
        header, columns, rows, total, nonfinite = parse_table(table, 1)
        self.assertEqual(header, "Time  total_x  total_y  total_z")
        self.assertEqual(columns, ("Time", "total_x", "total_y", "total_z"))
        self.assertEqual((rows, total, nonfinite), ([(3.0, 2.0, 3.0, 4.0)], 2, 1))


class OpenFOAMToolTests(unittest.IsolatedAsyncioTestCase):
    """Runs against a fake installation: a real bashrc and scripted applications."""

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name).resolve()
        foam = root / "foam"
        (foam / "etc").mkdir(parents=True)
        (foam / "etc/bashrc").write_text(
            "export WM_PROJECT=OpenFOAM WM_PROJECT_VERSION=12\n"
            f"export WM_PROJECT_DIR={foam} FOAM_APPBIN={foam}/bin\n"
            f"export FOAM_TUTORIALS={foam}/tutorials PATH={foam}/bin:$PATH\n"
        )
        for name, text in (
            ("solver.log", SOLVER_LOG),
            ("mesh.log", MESH_LOG),
            ("fatal.log", FATAL_LOG),
        ):
            (foam / name).write_text(text)
        script(foam / "bin/simpleFoam", f"cat {foam}/solver.log\nmkdir -p 100\n")
        script(foam / "bin/checkMesh", f"cat {foam}/mesh.log\n")
        script(foam / "bin/failFoam", f"cat {foam}/fatal.log\nexit 1\n")
        script(foam / "bin/slowFoam", "sleep 30\n")
        script(foam / "bin/envFoam", "env\n")
        script(
            foam / "bin/foamDictionary",
            'file="$1"; shift; echo "$*" >> "$file.calls"; echo "uniform (1 0 0)"\n',
        )
        tutorial = foam / "tutorials" / TUTORIAL
        (tutorial / "system").mkdir(parents=True)
        (tutorial / "0").mkdir()
        (tutorial / "system/controlDict").write_text("application simpleFoam;\n")
        (tutorial / "0/U").write_text("internalField uniform (0 0 0);\n")
        script(tutorial / "Allrun", f"echo ran > allrun.out\ncat {foam}/solver.log\n")
        self.bashrc = foam / "etc/bashrc"
        self.project = Project(root / "state", sandbox=root / "outputs")
        register_openfoam_tools(self.project, self.bashrc)
        await self.call("openfoam_copy_tutorial", tutorial=TUTORIAL, case="cases/pitz")
        self.case = self.project.sandbox / "cases/pitz"

    async def asyncTearDown(self):
        await self.project.drain()
        self.project.close()
        self.directory.cleanup()

    async def call(self, name: str, **arguments):
        return await self.project.call(self.project.tools.get(f"{name}@1"), arguments)

    async def run_app(self, application: str, **arguments):
        return await self.call(
            "openfoam_run", case="cases/pitz", application=application, **arguments
        )

    def test_environment_is_bashrc_over_a_minimal_host(self):
        os.environ["GUACAMOLE_TEST_SECRET"] = "leak"
        try:
            env = environment(self.bashrc)
        finally:
            del os.environ["GUACAMOLE_TEST_SECRET"]
        self.assertEqual(env["WM_PROJECT_VERSION"], "12")
        self.assertNotIn("GUACAMOLE_TEST_SECRET", env)

    async def test_tutorials_are_listed_copied_and_protected(self):
        info = await self.call("openfoam_info")
        self.assertEqual((info.fork, info.version), ("foundation", "12"))
        self.assertIn("simpleFoam", info.applications)
        self.assertEqual(
            await self.call("openfoam_tutorials", filter="pitz"), (TUTORIAL,)
        )
        self.assertTrue((self.case / "0/U").is_file())
        with self.assertRaisesRegex(ValueError, "pass replace"):
            await self.call(
                "openfoam_copy_tutorial", tutorial=TUTORIAL, case="cases/pitz"
            )
        with self.assertRaisesRegex(ValueError, "not a tutorial case"):
            await self.call("openfoam_copy_tutorial", tutorial="../etc", case="cases/x")

    async def test_dictionaries_go_through_foam_dictionary(self):
        edited = await self.call(
            "openfoam_set",
            case="cases/pitz",
            file="0/U",
            changes={"boundaryField/inlet/value": "uniform (10 0 0)"},
            remove=["boundaryField/old"],
        )
        self.assertEqual(Path(edited.path), self.case / "0/U")
        calls = (self.case / "0/U.calls").read_text().splitlines()
        self.assertEqual(
            calls,
            [
                "-entry boundaryField/inlet/value -set uniform (10 0 0)",
                "-entry boundaryField/old -remove",
            ],
        )
        value = await self.call(
            "openfoam_read", case="cases/pitz", file="0/U", entry="internalField"
        )
        self.assertEqual(value.strip(), "uniform (1 0 0)")
        with self.assertRaisesRegex(ValueError, "outside the case"):
            await self.call(
                "openfoam_read", case="cases/pitz", file="../../../foam/etc/bashrc"
            )

    async def test_runs_log_and_parse_solvers_meshes_and_failures(self):
        run = await self.run_app("simpleFoam", tolerance=1e-3)
        self.assertEqual(
            (run.returncode, run.residuals.verdict, run.times),
            (0, "converged", ("0", "100")),
        )
        self.assertTrue((self.case / "log.simpleFoam").is_file())
        mesh = await self.run_app("checkMesh")
        self.assertEqual((mesh.residuals, mesh.mesh.failed_checks), (None, 1))
        failed = await self.run_app("failFoam")
        self.assertEqual(failed.returncode, 1)
        self.assertTrue(failed.fatal_error.startswith("--> FOAM FATAL IO ERROR"))
        self.assertTrue(failed.fatal_error.endswith("FOAM exiting"))
        allrun = await self.run_app("./Allrun")
        self.assertEqual(allrun.application, "Allrun")
        self.assertTrue((self.case / "allrun.out").is_file())
        report = await self.call(
            "openfoam_residuals", case="cases/pitz", log="log.Allrun"
        )
        self.assertEqual(report.steps, 3)
        slow = await self.run_app("slowFoam", timeout_s=0.5)
        self.assertTrue(slow.timed_out)

    async def test_runs_see_only_the_openfoam_environment(self):
        os.environ["GUACAMOLE_TEST_SECRET"] = "leak"
        try:
            await self.run_app("envFoam")
        finally:
            del os.environ["GUACAMOLE_TEST_SECRET"]
        log = (self.case / "log.envFoam").read_text()
        self.assertIn("WM_PROJECT_VERSION=12", log)
        self.assertNotIn("GUACAMOLE_TEST_SECRET", log)

    async def test_runs_reject_escapes_and_unknown_programs(self):
        rejected = {
            "not an OpenFOAM application": {"application": "rm"},
            "do not pass -case": {"application": "simpleFoam", "args": ["-case", "x"]},
            "outside the sandbox": {
                "application": "simpleFoam",
                "args": ["-dict", "/etc/hosts"],
            },
            "outside the sandbox ": {
                "application": "simpleFoam",
                "args": ["../../../../x"],
            },
            "outside the case": {"application": "./../../x.sh"},
        }
        for message, arguments in rejected.items():
            with (
                self.subTest(message),
                self.assertRaisesRegex(ValueError, message.strip()),
            ):
                await self.run_app(**arguments)
        with self.assertRaisesRegex(ValueError, "escapes project sandbox"):
            await self.call(
                "openfoam_run", case="../elsewhere", application="simpleFoam"
            )

    def test_writes_need_a_plan_and_reads_do_not(self):
        tools = self.project.tools
        for name in (
            "openfoam_info",
            "openfoam_tutorials",
            "openfoam_read",
            "openfoam_residuals",
            "openfoam_table",
        ):
            self.assertFalse(tools.get(f"{name}@1").definition.requires_plan)
        for name in ("openfoam_copy_tutorial", "openfoam_set", "openfoam_run"):
            self.assertTrue(tools.get(f"{name}@1").definition.requires_plan)
