"""One explicitly populated catalogue; annotations are the tool contracts."""

import dataclasses
import inspect
import json
import math
import re
from collections.abc import Awaitable, Callable
from typing import (
    Annotated,
    Any,
    Literal,
    TypeAliasType,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from pydantic import BaseModel, TypeAdapter, create_model

from ..contracts import JSON, Model, ToolGrant


def encode(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def finite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numerical value")
    if isinstance(value, dict):
        for child in value.values():
            finite(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            finite(child)


def check_type(annotation: object, seen: set[object] | None = None) -> None:
    """Reject holes before Pydantic can turn Any into an unrestricted schema."""
    seen = set() if seen is None else seen
    if annotation in (Any, object, inspect.Signature.empty, dict, list, tuple, set):
        raise TypeError(
            f"A complete, serializable annotation is required: {annotation}"
        )
    if annotation in seen:
        return
    seen.add(annotation)
    if isinstance(annotation, TypeAliasType):
        check_type(annotation.__value__, seen)
        return
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is dict and args and args[0] is not str:
        raise TypeError("Wire dictionaries require string keys")
    if origin is Literal:
        return
    if origin is Annotated:
        check_type(args[0], seen)
        return
    if isinstance(annotation, type) and (
        issubclass(annotation, BaseModel) or dataclasses.is_dataclass(annotation)
    ):
        for child in get_type_hints(annotation, include_extras=True).values():
            check_type(child, seen)
    for child in args:
        if child is not Ellipsis:
            check_type(child, seen)


class ToolDefinition(Model):
    grant: ToolGrant
    description: str
    tags: tuple[str, ...]
    input_schema: JSON
    output_schema: JSON
    retry_safe: bool


@dataclasses.dataclass(frozen=True)
class Tool[**P, R]:
    definition: ToolDefinition
    function: Callable[P, R | Awaitable[R]]
    inputs: type[BaseModel]
    output: TypeAdapter[R]

    @property
    def key(self) -> str:
        return self.definition.grant.key

    def arguments(self, payload: JSON) -> dict[str, object]:
        finite(payload)
        parsed = self.inputs.model_validate_json(
            encode(payload), strict=True, extra="forbid"
        )
        return {name: getattr(parsed, name) for name in type(parsed).model_fields}

    def result(self, result: object) -> R:
        checked = self.output.validate_python(result, strict=True, extra="forbid")
        data = self.output.dump_python(checked, mode="json", warnings="error")
        finite(data)
        # Revalidate nested model instances, including models with permissive configs.
        return self.output.validate_json(encode(data), strict=True, extra="forbid")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool[..., Any]] = {}
        self.schemas: dict[str, TypeAdapter] = {}

    @overload
    def register[**P, R](
        self,
        function: Callable[P, Awaitable[R]],
        *,
        name: str | None = None,
        version: str = "1",
        description: str | None = None,
        tags: tuple[str, ...] = (),
        retry_safe: bool = False,
    ) -> Tool[P, R]: ...

    @overload
    def register[**P, R](
        self,
        function: Callable[P, R],
        *,
        name: str | None = None,
        version: str = "1",
        description: str | None = None,
        tags: tuple[str, ...] = (),
        retry_safe: bool = False,
    ) -> Tool[P, R]: ...

    def register[**P, R](
        self,
        function: Callable[P, R | Awaitable[R]],
        *,
        name: str | None = None,
        version: str = "1",
        description: str | None = None,
        tags: tuple[str, ...] = (),
        retry_safe: bool = False,
    ) -> Tool[P, R]:
        name = name or getattr(function, "__name__", type(function).__name__)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", name):
            raise ValueError("Tool names must be stable identifiers")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", version):
            raise ValueError("Invalid tool version")
        grant = ToolGrant(name=name, version=version)
        if grant.key in self._tools:
            raise ValueError(f"Duplicate tool: {grant.key}")
        target = function if inspect.isroutine(function) else function.__call__
        hints = get_type_hints(target, include_extras=True)
        signature = inspect.signature(function)
        fields: dict[str, Any] = {}
        for key, parameter in signature.parameters.items():
            if parameter.kind not in (
                parameter.POSITIONAL_OR_KEYWORD,
                parameter.KEYWORD_ONLY,
            ):
                raise TypeError(
                    "Tool parameters must be named; wrap positional-only or variadic APIs"
                )
            annotation = hints.get(key, inspect.Signature.empty)
            check_type(annotation)
            default = (
                ...
                if parameter.default is inspect.Parameter.empty
                else parameter.default
            )
            fields[key] = (annotation, default)
        annotation = hints.get("return", inspect.Signature.empty)
        check_type(annotation)
        inputs = create_model(
            f"{name.replace('.', '_')}_Input", __config__=Model.model_config, **fields
        )
        output: TypeAdapter[R] = TypeAdapter(annotation)
        definition = ToolDefinition(
            grant=grant,
            description=description or inspect.getdoc(function) or name,
            tags=tags,
            input_schema=inputs.model_json_schema(),
            output_schema=output.json_schema(),
            retry_safe=retry_safe,
        )
        encode(definition.model_dump(mode="json"))
        tool = Tool[P, R](definition, function, inputs, output)
        self._tools[grant.key] = tool
        return tool

    def get(self, grant: ToolGrant | str) -> Tool[..., Any]:
        return self._tools[grant if isinstance(grant, str) else grant.key]

    def definitions(
        self, grants: tuple[ToolGrant, ...] | None = None
    ) -> tuple[ToolDefinition, ...]:
        tools = (
            self._tools.values() if grants is None else (self.get(g) for g in grants)
        )
        return tuple(t.definition for t in tools)

    def schema(self, name: str, annotation: object) -> None:
        if name in self.schemas:
            raise ValueError(f"Duplicate schema: {name}")
        check_type(annotation)
        adapter = TypeAdapter(annotation)
        encode(adapter.json_schema())
        self.schemas[name] = adapter

    def payload(self, name: str, value: object) -> object:
        finite(value)
        return self.schemas[name].validate_json(
            encode(value), strict=True, extra="forbid"
        )
