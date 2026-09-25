from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from enums.design_variable import DesignVariables
from enums.metric_variables import MetricVariables

from .numerical_operator_parser import NumericalOperatorParser
from .specifications import (
    Comparison,
    ConditionOp,
    ExprOp,
    Objective,
    ObjectiveKind,
    ObjectiveResult,
    Requirement,
    RequirementResult,
    ToleranceMode,
)

SystemVariables = MetricVariables | DesignVariables


class SystemSpecifications:
    def __init__(self) -> None:
        self.requirements: list[Requirement] = []
        self.objectives: list[Objective] = []
        self.operator_parser = NumericalOperatorParser(
            variable_resolver=self._parse_system_variable,
            variable_types=(MetricVariables, DesignVariables),
            variable_label="MetricVariables/DesignVariables",
        )

    def add_requirement(self, requirement: Requirement) -> None:
        self.requirements.append(requirement)

    def add_requirements(self, requirements: list[Requirement]) -> None:
        self.requirements.extend(requirements)

    def add_objective(self, objective: Objective) -> None:
        self.objectives.append(objective)

    def add_objectives(self, objectives: list[Objective]) -> None:
        self.objectives.extend(objectives)

    def load_specifications_from_json(self, filepath: str | Path) -> None:
        path = Path(filepath)
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        self._load_specifications_from_raw(raw)

    def load_specifications_from_dict(self, raw: dict[str, Any]) -> None:
        self._load_specifications_from_raw(raw)

    def _load_specifications_from_raw(self, raw: Any) -> None:
        self.requirements = []
        self.objectives = []

        if isinstance(raw, dict):
            raw_requirements = raw.get("requirements", raw.get("constraints", []))
            raw_objectives = raw.get("objectives", [])
        else:
            raw_requirements = raw
            raw_objectives = []

        if not isinstance(raw_requirements, list):
            raise ValueError("JSON must contain a list of requirements.")
        if not isinstance(raw_objectives, list):
            raise ValueError("JSON objectives must be a list.")
        self.add_requirements(
            [self._requirement_from_dict(item) for item in raw_requirements]
        )
        self.add_objectives(
            [
                self._objective_from_dict(item, index)
                for index, item in enumerate(raw_objectives, 1)
            ]
        )

    def load_requirements_from_json(self, filepath: str | Path) -> None:
        self.load_specifications_from_json(filepath)

    def check_compliance(self, data: dict[str, Any]) -> dict[str, Any]:
        results: list[RequirementResult] = []

        for req in self.requirements:
            try:
                value, details = self._evaluate_requirement(req, data)
                passed = self._compare(value, req)

                results.append(
                    RequirementResult(
                        req_id=req.req_id,
                        description=req.description,
                        passed=passed,
                        computed_value=float(value) if value is not None else None,
                        comparison=req.comparison,
                        threshold=req.threshold,
                        lower=req.lower,
                        upper=req.upper,
                        target=req.target,
                        tolerance=req.tolerance,
                        tolerance_mode=req.tolerance_mode,
                        units=req.units,
                        details=details,
                    )
                )

            except Exception as exc:
                results.append(
                    RequirementResult(
                        req_id=req.req_id,
                        description=req.description,
                        passed=False,
                        computed_value=None,
                        comparison=req.comparison,
                        threshold=req.threshold,
                        lower=req.lower,
                        upper=req.upper,
                        target=req.target,
                        tolerance=req.tolerance,
                        tolerance_mode=req.tolerance_mode,
                        units=req.units,
                        details={"error": str(exc)},
                    )
                )

        return {
            "overall_pass": all(result.passed for result in results),
            "results": results,
        }

    def evaluate_objectives(self, data: dict[str, Any]) -> dict[str, Any]:
        results: list[ObjectiveResult] = []

        for obj in self.objectives:
            try:
                value, details = self._evaluate_objective(obj, data)
                results.append(
                    ObjectiveResult(
                        obj_id=obj.obj_id,
                        description=obj.description,
                        kind=obj.kind,
                        computed_value=float(value) if value is not None else None,
                        units=obj.units,
                        details=details,
                    )
                )
            except Exception as exc:
                results.append(
                    ObjectiveResult(
                        obj_id=obj.obj_id,
                        description=obj.description,
                        kind=obj.kind,
                        computed_value=None,
                        units=obj.units,
                        details={"error": str(exc)},
                    )
                )

        return {
            "values": tuple(result.computed_value for result in results),
            "results": results,
        }

    def evaluate_specifications(self, data: dict[str, Any]) -> dict[str, Any]:
        compliance = self.check_compliance(data)
        objectives = self.evaluate_objectives(data)
        return {
            "overall_pass": compliance["overall_pass"],
            "requirements": compliance["results"],
            "objectives": objectives["results"],
            "objective_values": objectives["values"],
        }

    def print_summary(self, report: dict[str, Any]) -> None:
        results = report.get("requirements", report.get("results", []))
        objectives = report.get("objectives", [])

        overall_pass = bool(report.get("overall_pass", False))
        total = len(results)
        passed = sum(1 for result in results if result.passed)
        failed = total - passed

        print(
            f"System Specifications Summary: {('PASS' if overall_pass else 'FAIL')}\n"
            f'Requirements: Passed: {passed}/{total} | Failed: {failed}'
        )

        if objectives:
            print(f"Objectives: {len(objectives)} detected")

        if total == 0:
            print("No requirements detected in report.")
            return

        print("-" * 80)

        for result in results:
            status = "PASS" if result.passed else "FAIL"
            computed_value = self._format_summary_value(
                result.computed_value, result.units
            )
            expected = self._format_requirement_expectation(result)

            print(
                f'[{status}] {result.req_id}: {result.description}\n'
                f'  Computed: {computed_value}\n'
                f'  Expected: {expected}'
            )

            if result.details:
                error = result.details.get("error")
                if error:
                    print(f"  Error:    {error}")

            print()

    def _requirement_from_dict(self, data: dict[str, Any]) -> Requirement:
        comparison = self._parse_comparison(
            data.get("comparison", data.get("operator"))
        )

        tolerance_mode = None
        if "tolerance_mode" in data and data["tolerance_mode"] is not None:
            tolerance_mode = self._parse_tolerance_mode(data["tolerance_mode"])

        expr = data.get("expr")
        if expr is None:
            expr = {"signal": data["output"]}
        expr = self._normalize_expr(expr)
        req_id = data.get("req_id", data.get("id", data.get("output", "requirement")))
        description = data.get("description", f"Requirement for {req_id}")

        return Requirement(
            req_id=req_id,
            description=description,
            expr=expr,
            comparison=comparison,
            threshold=data.get("threshold", data.get("value")),
            lower=data.get("lower"),
            upper=data.get("upper"),
            target=data.get("target"),
            tolerance=data.get("tolerance"),
            tolerance_mode=tolerance_mode,
            phase=data.get("phase"),
            units=data.get("units"),
        )

    def _objective_from_dict(self, data: dict[str, Any], index: int) -> Objective:
        obj_id = data.get(
            "obj_id", data.get("id", data.get("output", f"objective_{index}"))
        )
        expr = data.get("expr")
        if expr is None:
            expr = {"signal": data["output"]}
        expr = self._normalize_expr(expr)

        return Objective(
            obj_id=obj_id,
            description=data.get("description", f"Objective for {obj_id}"),
            expr=expr,
            kind=self._parse_objective_kind(data["kind"]),
            phase=data.get("phase"),
            units=data.get("units"),
        )

    def _normalize_expr(self, expr: Any) -> Any:
        return self.operator_parser.normalize_expr(expr)

    def _evaluate_requirement(
        self,
        req: Requirement,
        data: dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        values = self._eval_expr(req.expr, data)
        values = np.asarray(values)

        if values.ndim == 0:
            return float(values), {"type": "scalar"}

        if req.phase is not None:
            if req.phase not in data:
                raise KeyError(f"Phase mask '{req.phase}' not found in data.")

            mask = np.asarray(data[req.phase], dtype=bool)
            if len(mask) != len(values):
                raise ValueError(
                    f"Phase mask length {len(mask)} does not match series length {len(values)}."
                )

            values = values[mask]

        if len(values) == 0:
            raise ValueError("No samples available after phase filtering.")

        details = {
            "type": "series",
            "min_value": float(np.min(values)),
            "max_value": float(np.max(values)),
            "mean_value": float(np.mean(values)),
            "std_value": float(np.std(values)),
        }

        match req.comparison:
            case (
                Comparison.LT
                | Comparison.LE
                | Comparison.BETWEEN
                | Comparison.WITHIN_TOLERANCE
            ):
                details["aggregation_used"] = "max"
                return float(np.max(values)), details

            case Comparison.GT | Comparison.GE:
                details["aggregation_used"] = "min"
                return float(np.min(values)), details

            case Comparison.EQ | Comparison.NE:
                details["aggregation_used"] = "mean"
                return float(np.mean(values)), details

            case _:
                raise ValueError(f"Unsupported comparison {req.comparison}.")

    def _evaluate_objective(
        self,
        obj: Objective,
        data: dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        values = self._eval_expr(obj.expr, data)
        values = np.asarray(values)

        if values.ndim == 0:
            return float(values), {"type": "scalar"}

        if obj.phase is not None:
            if obj.phase not in data:
                raise KeyError(f"Phase mask '{obj.phase}' not found in data.")

            mask = np.asarray(data[obj.phase], dtype=bool)
            if len(mask) != len(values):
                raise ValueError(
                    f"Phase mask length {len(mask)} does not match series length {len(values)}."
                )

            values = values[mask]

        if len(values) == 0:
            raise ValueError("No samples available after phase filtering.")

        details = {
            "type": "series",
            "aggregation_used": "mean",
            "min_value": float(np.min(values)),
            "max_value": float(np.max(values)),
            "mean_value": float(np.mean(values)),
            "std_value": float(np.std(values)),
        }
        return float(np.mean(values)), details

    def _compare(self, value: float, req: Requirement) -> bool:
        match req.comparison:
            case Comparison.LT:
                return value < req.threshold

            case Comparison.LE:
                return value <= req.threshold

            case Comparison.GT:
                return value > req.threshold

            case Comparison.GE:
                return value >= req.threshold

            case Comparison.EQ:
                return bool(np.isclose(value, req.threshold))

            case Comparison.NE:
                return not bool(np.isclose(value, req.threshold))

            case Comparison.BETWEEN:
                return req.lower <= value <= req.upper

            case Comparison.WITHIN_TOLERANCE:
                lower, upper = self._tolerance_bounds(
                    req.target,
                    req.tolerance,
                    req.tolerance_mode,
                )
                return lower <= value <= upper

            case _:
                raise ValueError(f"Unsupported comparison {req.comparison}.")

    def _tolerance_bounds(
        self,
        target: float,
        tolerance: float,
        tolerance_mode: ToleranceMode,
    ) -> tuple[float, float]:
        match tolerance_mode:
            case ToleranceMode.ABSOLUTE:
                return target - tolerance, target + tolerance

            case ToleranceMode.PERCENT:
                frac = tolerance / 100.0
                return target * (1.0 - frac), target * (1.0 + frac)

            case _:
                raise ValueError(f"Unsupported tolerance mode {tolerance_mode}.")

    def _eval_expr(self, expr: Any, data: dict[str, Any]) -> np.ndarray | float | int:
        return self.operator_parser.eval_expr(expr, data)

    def _eval_condition(self, expr: dict[str, Any], data: dict[str, Any]) -> np.ndarray:
        return self.operator_parser.eval_condition(expr, data)

    @staticmethod
    def _rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
        return NumericalOperatorParser.rolling_mean(x, window)

    @staticmethod
    def _parse_system_variable(value: str | SystemVariables) -> SystemVariables:
        if isinstance(value, (MetricVariables, DesignVariables)):
            return value

        if not isinstance(value, str):
            raise TypeError(
                "System variable must be str, MetricVariables, or DesignVariables, "
                f"got {type(value)}"
            )

        for enum_type in (MetricVariables, DesignVariables):
            try:
                return enum_type[value]
            except KeyError:
                pass

        matches: list[SystemVariables] = []
        for variable in MetricVariables:
            if value in (variable.path, variable.metric_key):
                matches.append(variable)
        for variable in DesignVariables:
            if value in (variable.path, variable.json_key):
                matches.append(variable)

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            valid_matches = ", ".join(match.name for match in matches)
            raise ValueError(
                f"Ambiguous system variable '{value}'. Matches: {valid_matches}"
            )

        valid_metric_names = ", ".join(m.name for m in MetricVariables)
        valid_design_names = ", ".join(d.name for d in DesignVariables)
        raise ValueError(
            f"Unsupported system variable '{value}'. Valid metric variables: "
            f"{valid_metric_names}. Valid design variables: {valid_design_names}"
        )

    _parse_metric_variable = _parse_system_variable

    @staticmethod
    def _parse_comparison(value: str) -> Comparison:
        mapping = {
            "<": Comparison.LT,
            "<=": Comparison.LE,
            ">": Comparison.GT,
            ">=": Comparison.GE,
            "==": Comparison.EQ,
            "!=": Comparison.NE,
            "between": Comparison.BETWEEN,
            "within_tolerance": Comparison.WITHIN_TOLERANCE,
        }
        try:
            return mapping[value]
        except KeyError as exc:
            raise ValueError(f"Unsupported comparison string '{value}'.") from exc

    @staticmethod
    def _parse_tolerance_mode(value: str) -> ToleranceMode:
        mapping = {
            "absolute": ToleranceMode.ABSOLUTE,
            "percent": ToleranceMode.PERCENT,
        }
        try:
            return mapping[value]
        except KeyError as exc:
            raise ValueError(f"Unsupported tolerance mode string '{value}'.") from exc

    @staticmethod
    def _parse_objective_kind(value: str) -> ObjectiveKind:
        mapping = {
            "min": ObjectiveKind.MINIMIZE,
            "minimize": ObjectiveKind.MINIMIZE,
            "minimise": ObjectiveKind.MINIMIZE,
            "max": ObjectiveKind.MAXIMIZE,
            "maximize": ObjectiveKind.MAXIMIZE,
            "maximise": ObjectiveKind.MAXIMIZE,
        }
        try:
            return mapping[value]
        except KeyError as exc:
            raise ValueError(f"Unsupported objective kind string '{value}'.") from exc

    @staticmethod
    def _parse_expr_op(value: str) -> ExprOp:
        return NumericalOperatorParser.parse_expr_op(value)

    @staticmethod
    def _parse_condition_op(value: str) -> ConditionOp:
        return NumericalOperatorParser.parse_condition_op(value)

    @staticmethod
    def _format_summary_value(value: float | None, units: str | None) -> str:
        if value is None:
            return "n/a"

        unit_suffix = SystemSpecifications._format_unit_suffix(units)
        return f"{value:.6g}{unit_suffix}"

    def _format_requirement_expectation(self, result: RequirementResult) -> str:
        unit_suffix = self._format_unit_suffix(result.units)

        match result.comparison:
            case Comparison.LT:
                return f"< {result.threshold:.6g}{unit_suffix}"

            case Comparison.LE:
                return f"<= {result.threshold:.6g}{unit_suffix}"

            case Comparison.GT:
                return f"> {result.threshold:.6g}{unit_suffix}"

            case Comparison.GE:
                return f">= {result.threshold:.6g}{unit_suffix}"

            case Comparison.EQ:
                return f"== {result.threshold:.6g}{unit_suffix}"

            case Comparison.NE:
                return f"!= {result.threshold:.6g}{unit_suffix}"

            case Comparison.BETWEEN:
                return f"between {result.lower:.6g} and {result.upper:.6g}{unit_suffix}"

            case Comparison.WITHIN_TOLERANCE:
                if result.tolerance_mode == ToleranceMode.PERCENT:
                    return (
                        f"within +/- {result.tolerance:.6g}% of "
                        f"{result.target:.6g}{unit_suffix}"
                    )
                return (
                    f"within +/- {result.tolerance:.6g} of "
                    f"{result.target:.6g}{unit_suffix}"
                )

            case _:
                raise ValueError(f"Unsupported comparison {result.comparison}.")

    @staticmethod
    def _format_unit_suffix(units: str | None) -> str:
        if units in (None, "", "-"):
            return ""
        return f" {units}"
