import importlib.util
import tempfile
import unittest
from pathlib import Path

from guacamole import Project
from guacamole.contracts import ProducedFile

MODEL = """
package Hopper {
    part def Base { part chassis; }
    part def Engine { part nozzle; }
    part def Tank;
    part def Vehicle :> Base {
        part engine : Engine;
        part spare : Tank;
    }
    part vehicle : Vehicle {
        part avionics;
        part redefines spare { part valve; }
    }
}
"""
ENGINE = "/Twin/Hopper/vehicle/engine"
GEOMETRY = """#usda 1.0
(
    defaultPrim = "Body"
    metersPerUnit = 1
    upAxis = "Z"
)

def Cube "Body"
{
    double size = 0.2
}
"""


@unittest.skipUnless(importlib.util.find_spec("pxr"), "needs usd-core (--extra usd)")
class TwinTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from guacamole.integrations.usd.twin import register_twin_tools

        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        (root / "brief.txt").write_text("A hopper with one engine.")
        self.project = Project(root / "state", sandbox=root / "outputs")
        self.brief = self.project.ingest(root / "brief.txt", source_id="brief")
        await self.commit(MODEL)
        register_twin_tools(self.project)

        def save(name: str, text: str) -> ProducedFile:
            path = self.project.output_path(Path("work") / name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            return ProducedFile.from_path(path)

        self.save = self.project.tools.register(save, show_errors=True)

    async def asyncTearDown(self):
        await self.project.drain()
        self.project.close()
        self.directory.cleanup()

    async def commit(self, text: str):
        await self.project.sysml.commit(
            summary="Fixture", files={"model.sysml": text}, derived_from=(self.brief,)
        )

    async def call(self, name: str, **arguments):
        return await self.project.call(self.project.tools.get(f"{name}@1"), arguments)

    async def produce(self, name: str, text: str):
        job = self.project.submit(self.save, {"name": name, "text": text})
        await job.collect()
        return next(
            s.ref
            for s in self.project.store.list("job_file")
            if s.data["producer_request"] == job.id
        )

    def stage(self):
        from pxr import Usd

        return Usd.Stage.Open(str(self.project.sandbox / "twin/twin.usda"))

    async def attach(self, domain="cad", **attachment):
        attachment.setdefault("prim", ENGINE)
        attachment.setdefault("labels", {"material": "Inconel 718"})
        return await self.call(
            "twin_attach",
            domain=domain,
            summary=f"{domain} fixture",
            sources=[self.brief.model_dump(mode="json")],
            attachments=[attachment],
        )

    async def test_base_layer_is_derived_from_the_sysml_revision(self):
        state = await self.call("twin_inspect")
        self.assertEqual(state.status, "current")
        prims = {p.prim: p for p in state.parts}
        self.assertEqual(
            set(prims),
            {
                "/Twin/Hopper/vehicle",
                "/Twin/Hopper/vehicle/avionics",
                "/Twin/Hopper/vehicle/chassis",
                ENGINE,
                f"{ENGINE}/nozzle",
                "/Twin/Hopper/vehicle/spare",
                "/Twin/Hopper/vehicle/spare/valve",
            },
        )
        self.assertEqual(prims[ENGINE].element, "Hopper::Vehicle::engine")
        self.assertEqual(prims[ENGINE].feature_path, "Hopper::vehicle.engine")
        self.assertEqual(
            prims["/Twin/Hopper/vehicle/spare"].definitions, ("Hopper::Tank",)
        )
        stage = self.stage()
        prim = stage.GetPrimAtPath(f"{ENGINE}/nozzle")
        self.assertEqual(
            prim.GetAttribute("guacamole:sysml:element").Get(), "Hopper::Engine::nozzle"
        )
        again = await self.call("twin_inspect")
        self.assertEqual(again.stage.sha256, state.stage.sha256)

    async def test_a_layer_records_provenance_and_composes_over_the_base(self):
        geometry = await self.produce("engine.usda", GEOMETRY)
        drawing = await self.produce("engine.txt", "drawing stand-in")
        status = await self.attach(
            geometry=geometry.model_dump(mode="json"),
            placement={"translate": [0, 0, -1.5], "rotate_xyz": [0, 0, 90]},
            values={"mass": {"value": 12.5, "unit": "kg"}},
            files={"drawing": drawing.model_dump(mode="json")},
        )
        self.assertEqual((status.status, status.author), ("current", "script"))
        record = self.project.store.resolve(status.ref)
        request = self.project.activity.get(record.data["request_id"])
        self.assertEqual(
            (request.target, request.status), ("twin_attach@1", "completed")
        )
        model = self.project.sysml.current().ref
        self.assertIn(model, record.dependencies)
        self.assertIn(geometry, record.dependencies)

        stage = self.stage()
        engine = stage.GetPrimAtPath(ENGINE)
        mass = engine.GetAttribute("guacamole:cad:mass")
        self.assertEqual((mass.Get(), mass.GetCustomDataByKey("unit")), (12.5, "kg"))
        self.assertEqual(
            engine.GetAttribute("xformOp:translate").Get(), (0.0, 0.0, -1.5)
        )
        geometry = stage.GetPrimAtPath(f"{ENGINE}/geometry_cad")
        self.assertTrue(geometry.HasPayload())
        stage.Load()
        geometry = stage.GetPrimAtPath(f"{ENGINE}/geometry_cad")
        self.assertEqual(geometry.GetTypeName(), "Cube")
        self.assertEqual(geometry.GetAttribute("size").Get(), 0.2)
        link = engine.GetAttribute("guacamole:cad:drawing").Get()
        self.assertTrue(Path(link.resolvedPath).read_text() == "drawing stand-in")
        data = stage.GetRootLayer().customLayerData["guacamole"]
        self.assertEqual(
            list(data["layers"]), [f"twin_layer:cad@1#{status.ref.sha256}"]
        )

    async def test_layers_cannot_add_structure_or_break_the_contract(self):
        flat = await self.produce(
            "flat.usda", GEOMETRY.replace('    upAxis = "Z"\n', "")
        )
        step = await self.produce("engine.step", "ISO-10303-21;")
        rejected = {
            "not a part prim": {"prim": f"{ENGINE}/injector"},
            "not a part prim of": {"prim": "/Twin/Hopper"},
            "Geometry must be USD": {"geometry": step.model_dump(mode="json")},
            "upAxis": {"geometry": flat.model_dump(mode="json")},
            "Attribute names must be identifiers": {"labels": {"bad name": "x"}},
        }
        for message, attachment in rejected.items():
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                await self.attach(**attachment)
        with self.assertRaisesRegex(ValueError, "base layer's namespace"):
            await self.attach("sysml")
        await self.attach(placement={"translate": [1, 0, 0]})
        with self.assertRaisesRegex(ValueError, "already places"):
            await self.attach("thermal", placement={"translate": [2, 0, 0]})
        cad = self.project.store.get("twin_layer", "cad").ref
        with self.assertRaisesRegex(ValueError, "its own earlier revision"):
            await self.call(
                "twin_attach",
                domain="cad",
                summary="x",
                sources=[cad.model_dump(mode="json")],
                attachments=[{"prim": ENGINE, "labels": {"a": "b"}}],
            )

    async def test_a_new_sysml_revision_stales_layers_until_rebased(self):
        await self.attach()
        await self.commit(MODEL.replace("part avionics;", "part avionics; part legs;"))
        state = await self.call("twin_inspect")
        self.assertEqual([l.status for l in state.layers], ["stale"])
        self.assertFalse((self.project.sandbox / "twin/layers/cad.usda").exists())
        stage = self.stage()
        self.assertTrue(stage.GetPrimAtPath("/Twin/Hopper/vehicle/legs").IsValid())

        rebased = await self.call("twin_rebase", domain="cad")
        self.assertEqual((rebased.status, rebased.ref.revision), ("current", 2))
        self.assertTrue((self.project.sandbox / "twin/layers/cad.usda").exists())

        await self.commit(MODEL.replace("part engine : Engine;", ""))
        with self.assertRaisesRegex(ValueError, "does not hold for the current model"):
            await self.call("twin_rebase", domain="cad")

    async def test_twin_files_are_rendered_from_records_not_read(self):
        status = await self.attach()
        path = self.project.sandbox / "twin/layers/cad.usda"
        path.write_text("#usda 1.0\n")
        await self.call("twin_inspect")
        self.assertEqual(ProducedFile.from_path(path).sha256, status.file.sha256)

    def test_writes_need_a_plan_and_reads_do_not(self):
        tools = self.project.tools
        self.assertFalse(tools.get("twin_inspect@1").definition.requires_plan)
        self.assertTrue(tools.get("twin_attach@1").definition.requires_plan)
        self.assertTrue(tools.get("twin_rebase@1").definition.requires_plan)
