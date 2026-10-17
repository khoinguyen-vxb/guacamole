"""A USD digital twin derived from the SysML model, with per-layer provenance.

The base layer is a pure function of the current SysML revision: one Xform per part
instance (structure.py), each linked to its SysML element. Domain layers (cad, cfd,
test, ...) are twin_layer records, written only through the tools registered here.
Each depends on the SysML revision it targets and every record it cites, so the
store stales it when any of them changes; twin_rebase re-checks a stale layer
against the current model. Domain layers only override base prims: they place
parts, add a USD geometry payload under a part, and attach values, labels and file
links in their own attribute namespace.

The files under sandbox/twin are re-rendered from those records on every twin tool
call and never read back, so editing them changes nothing:

    twin/twin.usda          root: sublayers every current domain layer, then base
    twin/base.usda          derived from SysML revision N
    twin/layers/<domain>.usda
"""

import asyncio
import re
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pxr import Gf, Sdf, Usd, UsdGeom, Vt
from pydantic import Field

from ...contracts import FileRecord, Model, ProducedFile, Quantity, Ref, SystemModel
from ...storage import Snapshot
from ...tools.execution import CURRENT_REQUEST
from ...tools.registry import encode
from ...tools.workspace import Offset
from ..sysml.registry import CITABLE
from .structure import ROOT, Node, derive

if TYPE_CHECKING:
    from ...project import Project

KIND = "twin_layer"
EXPORT = Path("twin")
PAGE = 200
FILE_KINDS = frozenset({"job_file", "source"})
SOURCE_KINDS = CITABLE | FILE_KINDS | {KIND}
USD_SUFFIXES = frozenset({".usd", ".usda", ".usdc", ".usdz"})
KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

type Domain = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
type Text = Annotated[str, Field(min_length=1)]
type Vector = tuple[float, float, float]


class Placement(Model):
    """The part's transform in its parent part's frame: metres and degrees."""

    translate: Vector = (0.0, 0.0, 0.0)
    rotate_xyz: Vector = (0.0, 0.0, 0.0)


class Attachment(Model):
    """What one domain layer says about one part prim."""

    prim: str
    geometry: Ref | None = None  # A job_file/source .usd(a|c|z) in metres, Z up
    placement: Placement | None = None
    values: dict[str, Quantity] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    files: dict[str, Ref] = Field(default_factory=dict)  # Any artifact, linked


class TwinLayer(Model):
    """One revision of a domain layer: its content and where it came from."""

    domain: str
    summary: str
    sources: tuple[Ref, ...]
    attachments: tuple[Attachment, ...]
    system_model: Ref
    author: str
    request_id: str | None


class TwinPart(Model):
    prim: str
    element: str
    element_id: str
    feature_path: str
    definitions: tuple[str, ...]
    multiplicity: str
    recursive: bool


class TwinLayerStatus(Model):
    domain: str
    ref: Ref
    status: Literal["current", "stale"]
    summary: str
    author: str
    request_id: str | None
    attachments: int
    file: ProducedFile | None  # The rendered layer, while it is current


class TwinState(Model):
    system_model: Ref | None
    status: Literal["missing", "stale", "current"]
    parts: tuple[TwinPart, ...]
    total_parts: int
    layers: tuple[TwinLayerStatus, ...]
    stage: ProducedFile | None


def cite(ref: Ref) -> str:
    return f"{ref.kind}:{ref.id}@{ref.revision}#{ref.sha256}"


def _uniform(prim: Usd.Prim, name: str, kind: Sdf.ValueTypeName, value: object) -> None:
    prim.CreateAttribute(
        name, kind, custom=True, variability=Sdf.VariabilityUniform
    ).Set(value)


def _layer() -> tuple[Sdf.Layer, Usd.Stage]:
    layer = Sdf.Layer.CreateAnonymous(".usda")
    # Payloads resolve against the exported file, never this anonymous layer.
    stage = Usd.Stage.Open(layer, Usd.Stage.LoadNone)
    UsdGeom.SetStageMetersPerUnit(stage, UsdGeom.LinearUnits.meters)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    return layer, stage


def render_base(nodes: Iterable[Node], model: Ref, digest: str) -> str:
    layer, stage = _layer()
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, f"/{ROOT}").GetPrim())
    for node in nodes:
        schema = UsdGeom.Scope if node.kind == "package" else UsdGeom.Xform
        prim = schema.Define(stage, node.prim).GetPrim()
        _uniform(
            prim, "guacamole:sysml:element", Sdf.ValueTypeNames.String, node.element
        )
        _uniform(
            prim,
            "guacamole:sysml:elementId",
            Sdf.ValueTypeNames.String,
            node.element_id,
        )
        _uniform(
            prim,
            "guacamole:sysml:featurePath",
            Sdf.ValueTypeNames.String,
            node.feature_path,
        )
        if node.definitions:
            _uniform(
                prim,
                "guacamole:sysml:definitions",
                Sdf.ValueTypeNames.StringArray,
                list(node.definitions),
            )
        if node.multiplicity:
            _uniform(
                prim,
                "guacamole:sysml:multiplicity",
                Sdf.ValueTypeNames.String,
                node.multiplicity,
            )
        if node.recursive:
            _uniform(prim, "guacamole:sysml:recursive", Sdf.ValueTypeNames.Bool, True)
    layer.customLayerData = {
        "guacamole": {
            "kind": "base",
            "system_model": cite(model),
            "model_digest": digest,
        }
    }
    return layer.ExportToString()


def render_layer(layer: TwinLayer, ref: Ref, files: dict[str, FileRecord]) -> str:
    """files maps cite(ref) to the FileRecord of every geometry and file ref."""
    output, stage = _layer()

    def asset(file_ref: Ref) -> str:
        # Layers live at twin/layers/; artifact paths are sandbox-relative.
        return "../../" + files[cite(file_ref)].path

    namespace = f"guacamole:{layer.domain}"
    for attachment in layer.attachments:
        prim = stage.OverridePrim(attachment.prim)
        if attachment.placement is not None:
            xform = UsdGeom.Xformable(prim)
            xform.AddTranslateOp().Set(Gf.Vec3d(*attachment.placement.translate))
            xform.AddRotateXYZOp().Set(Gf.Vec3f(*attachment.placement.rotate_xyz))
        if attachment.geometry is not None:
            # Typeless, so the payload's own prim type (Mesh, Xform...) composes.
            geometry = stage.DefinePrim(f"{attachment.prim}/geometry_{layer.domain}")
            geometry.GetPayloads().AddPayload(asset(attachment.geometry))
            geometry.SetCustomDataByKey("guacamole:source", cite(attachment.geometry))
        for key, quantity in sorted(attachment.values.items()):
            attribute = prim.CreateAttribute(
                f"{namespace}:{key}", Sdf.ValueTypeNames.Double, custom=True
            )
            attribute.Set(quantity.value)
            attribute.SetCustomDataByKey("unit", quantity.unit)
            if quantity.frame is not None:
                attribute.SetCustomDataByKey("frame", quantity.frame)
        for key, text in sorted(attachment.labels.items()):
            _uniform(prim, f"{namespace}:{key}", Sdf.ValueTypeNames.String, text)
        for key, file_ref in sorted(attachment.files.items()):
            attribute = prim.CreateAttribute(
                f"{namespace}:{key}",
                Sdf.ValueTypeNames.Asset,
                custom=True,
                variability=Sdf.VariabilityUniform,
            )
            attribute.Set(Sdf.AssetPath(asset(file_ref)))
            attribute.SetCustomDataByKey("guacamole:source", cite(file_ref))
    output.customLayerData = {
        "guacamole": {
            "kind": "domain",
            "domain": layer.domain,
            "summary": layer.summary,
            "record": cite(ref),
            "system_model": cite(layer.system_model),
            "author": layer.author,
            "request_id": layer.request_id or "",
            "sources": Vt.StringArray([cite(s) for s in layer.sources]),
        }
    }
    return output.ExportToString()


def render_root(model: Ref, layers: Iterable[tuple[str, Ref]]) -> str:
    layers = list(layers)
    root = Sdf.Layer.CreateAnonymous(".usda")
    root.subLayerPaths = [f"layers/{domain}.usda" for domain, _ in layers] + [
        "base.usda"
    ]
    root.defaultPrim = ROOT
    root.pseudoRoot.SetInfo(UsdGeom.Tokens.metersPerUnit, 1.0)
    root.pseudoRoot.SetInfo(UsdGeom.Tokens.upAxis, UsdGeom.Tokens.z)
    root.customLayerData = {
        "guacamole": {
            "kind": "root",
            "system_model": cite(model),
            "layers": Vt.StringArray([cite(ref) for _, ref in layers]),
        }
    }
    return root.ExportToString()


def _check_asset(path: Path) -> None:
    """A geometry payload must compose: a default prim, metres, Z up."""
    layer = Sdf.Layer.FindOrOpen(str(path))
    if layer is None:
        raise ValueError(f"USD cannot open geometry {path.name}")
    if not layer.defaultPrim:
        raise ValueError(f"Geometry {path.name} needs a defaultPrim to be a payload")
    root = layer.pseudoRoot
    meters = root.GetInfo("metersPerUnit") if root.HasInfo("metersPerUnit") else None
    axis = root.GetInfo("upAxis") if root.HasInfo("upAxis") else None
    if meters != 1.0 or axis != "Z":
        raise ValueError(
            f'Geometry {path.name} must author metersPerUnit = 1 and upAxis = "Z"; '
            f"it has {meters} and {axis!r} (USD's unauthored defaults are cm and Y)"
        )


class Twin:
    def __init__(self, project: "Project") -> None:
        self.project = project
        self._base: tuple[Ref, tuple[Node, ...], str] | None = None

    def _model(self, *, current: bool) -> Snapshot:
        snapshot = self.project.sysml.current()
        if snapshot is None:
            raise ValueError(
                "No SysML model yet: the twin derives from the systems engineer's model"
            )
        if current and snapshot.stale:
            raise ValueError(
                f"SysML model revision {snapshot.ref.revision} is stale; twin layers "
                "attach to a current model once the systems engineer revalidates it"
            )
        return snapshot

    async def _structure(self, snapshot: Snapshot) -> tuple[tuple[Node, ...], str]:
        if self._base is None or self._base[0] != snapshot.ref:
            model = SystemModel.model_validate_json(encode(snapshot.data))

            def build() -> tuple[tuple[Node, ...], str]:
                nodes = derive(model.files)
                return nodes, render_base(nodes, snapshot.ref, model.report.digest)

            self._base = (snapshot.ref, *await asyncio.to_thread(build))
        return self._base[1], self._base[2]

    def _layers(self) -> list[tuple[Snapshot, TwinLayer]]:
        layers = [
            (s, TwinLayer.model_validate_json(encode(s.data)))
            for s in self.project.store.list(KIND)
        ]
        return sorted(layers, key=lambda pair: pair[1].domain)

    def _file(self, ref: Ref) -> FileRecord:
        if ref.kind not in FILE_KINDS:
            raise ValueError(f"Files are job_file or source records, not {ref.kind}")
        return FileRecord.model_validate_json(
            encode(self.project.store.resolve(ref).data)
        )

    def _write(self, path: Path, text: str) -> ProducedFile:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
        return ProducedFile.from_path(path)

    def _export(
        self, model: Snapshot, base: str
    ) -> tuple[ProducedFile, dict[str, ProducedFile]]:
        """Re-render every file under twin/ from the records."""
        output = self.project.output_path
        # A new or invalidated SysML revision stales every layer that targets it.
        current = [(s, layer) for s, layer in self._layers() if not s.stale]
        written = {}
        for snapshot, layer in current:
            refs = [
                r
                for a in layer.attachments
                for r in (
                    *((a.geometry,) if a.geometry else ()),
                    *a.files.values(),
                )
            ]
            text = render_layer(
                layer, snapshot.ref, {cite(r): self._file(r) for r in refs}
            )
            written[layer.domain] = self._write(
                output(EXPORT / "layers" / f"{layer.domain}.usda"), text
            )
        layers = output(EXPORT / "layers")
        for path in layers.glob("*.usda") if layers.is_dir() else ():
            if path.stem not in written:
                path.unlink()
        self._write(output(EXPORT / "base.usda"), base)
        root = render_root(model.ref, ((l.domain, s.ref) for s, l in current))
        return self._write(output(EXPORT / "twin.usda"), root), written

    def _status(
        self, snapshot: Snapshot, layer: TwinLayer, file: ProducedFile | None
    ) -> TwinLayerStatus:
        return TwinLayerStatus(
            domain=layer.domain,
            ref=snapshot.ref,
            status="stale" if snapshot.stale else "current",
            summary=layer.summary,
            author=layer.author,
            request_id=layer.request_id,
            attachments=len(layer.attachments),
            file=file,
        )

    async def state(self, offset: int) -> TwinState:
        snapshot = self.project.sysml.current()
        if snapshot is None:
            return TwinState(
                system_model=None,
                status="missing",
                parts=(),
                total_parts=0,
                layers=tuple(self._status(s, l, None) for s, l in self._layers()),
                stage=None,
            )
        nodes, base = await self._structure(snapshot)
        stage, files = self._export(snapshot, base)
        parts = [n for n in nodes if n.kind == "part"]
        return TwinState(
            system_model=snapshot.ref,
            status="stale" if snapshot.stale else "current",
            parts=tuple(
                TwinPart(
                    prim=n.prim,
                    element=n.element,
                    element_id=n.element_id,
                    feature_path=n.feature_path,
                    definitions=n.definitions,
                    multiplicity=n.multiplicity,
                    recursive=n.recursive,
                )
                for n in parts[offset : offset + PAGE]
            ),
            total_parts=len(parts),
            layers=tuple(
                self._status(s, l, files.get(l.domain)) for s, l in self._layers()
            ),
            stage=stage,
        )

    async def attach(
        self,
        domain: str,
        summary: str,
        sources: tuple[Ref, ...],
        attachments: tuple[Attachment, ...],
    ) -> TwinLayerStatus:
        store, model = self.project.store, self._model(current=True)
        nodes, base = await self._structure(model)
        prims = {n.prim for n in nodes}
        parts = {n.prim for n in nodes if n.kind == "part"}
        if domain == "sysml":
            raise ValueError("sysml is the base layer's namespace; name another domain")
        if not sources:
            raise ValueError("Cite the records this layer derives from in sources")
        if not attachments:
            raise ValueError("A layer attaches something to at least one part")
        for ref in sources:
            if ref.kind not in SOURCE_KINDS:
                raise ValueError(f"sources cite engineering records, not {ref.kind}")
            if ref.kind == KIND and ref.id == domain:
                raise ValueError("A layer cannot cite its own earlier revision")
            store.resolve(ref, current=True)
        seen: set[str] = set()
        files: list[Ref] = []
        for attachment in attachments:
            prim = attachment.prim
            if prim not in parts:
                raise ValueError(
                    f"{prim} is not a part prim of SysML revision {model.ref.revision}; "
                    "twin_inspect lists them"
                )
            if prim in seen:
                raise ValueError(f"{prim} appears twice; give it one attachment")
            seen.add(prim)
            if not (
                attachment.geometry
                or attachment.placement
                or attachment.values
                or attachment.labels
                or attachment.files
            ):
                raise ValueError(f"The attachment to {prim} attaches nothing")
            keys = [*attachment.values, *attachment.labels, *attachment.files]
            if bad := [k for k in keys if not KEY.fullmatch(k) or len(k) > 64]:
                raise ValueError(f"Attribute names must be identifiers: {bad}")
            if len(set(keys)) != len(keys):
                raise ValueError(f"{prim} uses an attribute name twice")
            if attachment.geometry is not None:
                if f"{prim}/geometry_{domain}" in prims:
                    raise ValueError(
                        f"{prim} has a SysML part named geometry_{domain}; "
                        "use another domain name"
                    )
                path = self.project.verify_file(self._file(attachment.geometry))
                if path.suffix.lower() not in USD_SUFFIXES:
                    raise ValueError(
                        f"Geometry must be USD ({', '.join(sorted(USD_SUFFIXES))}); "
                        f"link {path.name} under files instead"
                    )
                await asyncio.to_thread(_check_asset, path)
                files.append(attachment.geometry)
            for ref in attachment.files.values():
                self.project.verify_file(self._file(ref))
                files.append(ref)
        for ref in files:
            store.resolve(ref, current=True)
        placed = {a.prim for a in attachments if a.placement is not None}
        for snapshot, other in self._layers():
            if snapshot.stale or other.domain == domain:
                continue
            others = {a.prim for a in other.attachments if a.placement is not None}
            if clash := placed & others:
                raise ValueError(
                    f"Layer {other.domain} already places {sorted(clash)}; one layer "
                    "places each part"
                )
        request_id = CURRENT_REQUEST.get()
        author = (
            self.project.activity.get(request_id).requester if request_id else "script"
        )
        layer = TwinLayer(
            domain=domain,
            summary=summary,
            sources=sources,
            attachments=attachments,
            system_model=model.ref,
            author=author,
            request_id=request_id,
        )
        ref = store.put(
            KIND,
            domain,
            layer,
            actor=author,
            dependencies=tuple(dict.fromkeys((model.ref, *sources, *files))),
            request_id=request_id,
        )
        _, written = self._export(model, base)
        return self._status(store.resolve(ref), layer, written.get(domain))

    async def rebase(self, domain: str) -> TwinLayerStatus:
        snapshot = self.project.store.maybe(KIND, domain)
        if snapshot is None:
            raise ValueError(f"No twin layer {domain}")
        if not snapshot.stale:
            raise ValueError(f"Layer {domain} is already current")
        layer = TwinLayer.model_validate_json(encode(snapshot.data))
        try:
            return await self.attach(
                domain, layer.summary, layer.sources, layer.attachments
            )
        except ValueError as exc:
            raise ValueError(
                f"Layer {domain} does not hold for the current model: {exc}. Attach a "
                "new revision citing current records"
            ) from None


def register_twin_tools(project: "Project") -> None:
    """Register twin_inspect, twin_attach and twin_rebase."""
    twin = Twin(project)

    async def twin_inspect(offset: Offset = 0) -> TwinState:
        """The digital twin: the SysML revision it derives from, its part prims, and
        every domain layer with its provenance and status.

        Re-renders sandbox/twin from the records (twin.usda is the composed stage;
        read it, or the layer files, with read_text). parts lists 200 part prims
        from offset; total_parts counts them all. Each part prim is one SysML part
        instance: feature_path names it in SysML, element is the declaring element.
        A stale layer no longer composes: its SysML revision or a cited record
        changed; use twin_rebase, or attach a new revision.
        """
        return await twin.state(offset)

    async def twin_attach(
        domain: Domain,
        summary: Text,
        sources: tuple[Ref, ...],
        attachments: tuple[Attachment, ...],
    ) -> TwinLayerStatus:
        """Record a new revision of one domain's layer (cad, cfd, thermal, test...).

        The layer replaces that domain's previous revision. It can only override
        part prims twin_inspect lists, never add structure: change the SysML model
        for that. Per part prim it can give a placement (metres, degrees XYZ, in
        the parent part's frame; one layer places each part), a USD geometry
        payload (a job_file/source .usd/.usda/.usdc/.usdz authoring metersPerUnit
        = 1, upAxis = "Z" and a defaultPrim), and values (quantities with units),
        labels and files (any artifact, linked), stored as guacamole:<domain>:<name>.
        sources cites the records the layer derives from (evidence, tool_result,
        decision, job_file, other twin layers, ...); revising any of them, or the
        SysML model, stales the layer. Attaching is not physical validation.
        """
        return await twin.attach(domain, summary, sources, attachments)

    async def twin_rebase(domain: Domain) -> TwinLayerStatus:
        """Re-record a stale layer unchanged against the current SysML revision.

        Succeeds only if every part prim it attaches to still exists and every
        record it cites is still current; otherwise attach a new revision.
        """
        return await twin.rebase(domain)

    # Errors name prims, refs and paths in the sandbox, never secrets.
    project.tools.register(
        twin_inspect, retry_safe=True, requires_plan=False, show_errors=True
    )
    for function in (twin_attach, twin_rebase):
        project.tools.register(function, show_errors=True)
