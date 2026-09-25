from __future__ import annotations

from enum import Enum


class ReferenceFrame(str, Enum):
    NOSE_TO_TAIL = "nose_to_tail"
    NOZZLE_TO_COMBUSTION_CHAMBER = "nozzle_to_combustion_chamber"
    TIP_OF_PARENT_COMPONENT = "tip_of_parent_component"
    BOTTOM_OF_PARENT_COMPONENT = "bottom_of_parent_component"

    @classmethod
    def from_value(cls, value: "ReferenceFrame | str") -> "ReferenceFrame":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError as exc:
                valid = ", ".join(member.value for member in cls)
                raise ValueError(
                    f"Unknown reference_frame '{value}'. Valid frames: {valid}"
                ) from exc
        raise TypeError(
            f"reference_frame must be a {cls.__name__} or str, got {type(value).__name__}"
        )


class ComponentType(str, Enum):
    AXISYMMETRIC = "axisymmetric"
    WING = "wing"
    PROTRUSION = "protrusion"

    @classmethod
    def from_value(cls, value: "ComponentType | str") -> "ComponentType":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError as exc:
                valid = ", ".join(member.value for member in cls)
                raise ValueError(
                    f"Unknown component_type '{value}'. Valid types: {valid}"
                ) from exc
        raise TypeError(
            f"component_type must be a {cls.__name__} or str, got {type(value).__name__}"
        )


class CADComponentType(str, Enum):
    DIVERGING_CONICAL_NOZZLE = "diverging_conical_nozzle"
    CONVERGING_DIVERGING_CONICAL_NOZZLE = "converging_diverging_conical_nozzle"
    HYBRID_FUEL_GRAIN = "hybrid_fuel_grain"
    CYLINDRICAL_TANK = "cylindrical_tank"
    CAPPED_CYLINDRICAL_TANK = "capped_cylindrical_tank"
    VONKARMAN_NOSECONE = "vonkarman_nosecone"
    OGIVE_NOSECONE = "ogive_nosecone"
    CONICAL_NOSECONE = "conical_nosecone"
    LVHAACK_NOSECONE = "lvhaack_nosecone"
    BODY_TUBE = "body_tube"
    TUBE_COUPLER = "tube_coupler"
    BULKHEAD = "bulkhead"
    MASS_COMPONENT = "mass_component"
    SHOCK_CORD = "shock_cord"
    DROGUE_PARACHUTE = "drogue_parachute"
    MAIN_PARACHUTE = "main_parachute"
    VONKARMAN_BOATTAIL = "vonkarman_boattail"
    CONICAL_BOATTAIL = "conical_boattail"
    TRAPEZOIDAL_FINS = "trapezoidal_fins"
    WING = "wing"
    RAIL_BUTTON = "rail_button"
    LAUNCH_RAIL = "launch_rail"

    @classmethod
    def from_value(cls, value: "CADComponentType | str") -> "CADComponentType":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError as exc:
                valid = ", ".join(member.value for member in cls)
                raise ValueError(
                    f"Unknown CAD component type '{value}'. Valid types: {valid}"
                ) from exc
        raise TypeError(
            f"CAD component type must be a {cls.__name__} or str, got {type(value).__name__}"
        )


REFERENCE_FRAMES = tuple(member.value for member in ReferenceFrame)
