from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from .specifications import ConditionOp, ExprOp


VariableResolver = Callable[[str], Any]


class NumericalOperatorParser:
    def __init__(
        self,
        *,
        variable_resolver: VariableResolver | None = None,
        variable_types: tuple[type[Any], ...] = (),
        variable_label: str = "variable",
    ) -> None:
        self.variable_resolver = variable_resolver
        self.variable_types = variable_types
        self.variable_label = variable_label

    def normalize_expr(self, expr: Any) -> Any:
        if isinstance(expr, (int, float)):
            return expr

        if self._is_variable(expr):
            return expr

        if not isinstance(expr, dict):
            raise TypeError(
                f"Expression must be dict/int/float/{self.variable_label}, "
                f"got {type(expr)}"
            )

        expr = dict(expr)

        if "op" in expr and isinstance(expr["op"], str):
            expr["op"] = self.parse_expr_op(expr["op"])

        if "signal" in expr:
            expr["signal"] = self.parse_variable(expr["signal"])

        for key, value in expr.items():
            if isinstance(value, dict):
                expr[key] = self.normalize_expr(value)

        return expr

    def eval_expr(self, expr: Any, data: dict[str, Any]) -> np.ndarray | float | int:
        if isinstance(expr, (int, float)):
            return float(expr)

        if self._is_variable(expr):
            return np.asarray(expr.get_value(data), dtype=float)

        if not isinstance(expr, dict):
            raise TypeError(
                f"Expression must be dict/int/float/{self.variable_label}, "
                f"got {type(expr)}"
            )

        if "const" in expr:
            return float(expr["const"])

        if "signal" in expr:
            variable = expr["signal"]
            if not self._is_variable(variable):
                raise TypeError(
                    f"'signal' must resolve to {self.variable_label}, "
                    f"got {type(variable)}"
                )
            return np.asarray(variable.get_value(data), dtype=float)

        op = expr.get("op")
        if isinstance(op, str):
            op = self.parse_expr_op(op)
        if op is None:
            raise ValueError("Expression must contain 'const', 'signal', or 'op'.")

        match op:
            case ExprOp.ADD:
                return self.eval_expr(expr["left"], data) + self.eval_expr(
                    expr["right"], data
                )
            case ExprOp.SUB:
                return self.eval_expr(expr["left"], data) - self.eval_expr(
                    expr["right"], data
                )
            case ExprOp.MUL:
                return self.eval_expr(expr["left"], data) * self.eval_expr(
                    expr["right"], data
                )
            case ExprOp.DIV:
                left = np.asarray(self.eval_expr(expr["left"], data), dtype=float)
                right = np.asarray(self.eval_expr(expr["right"], data), dtype=float)
                return left / np.maximum(np.abs(right), 1e-12)
            case ExprOp.POW:
                left = np.asarray(self.eval_expr(expr["left"], data), dtype=float)
                right = np.asarray(self.eval_expr(expr["right"], data), dtype=float)
                return left**right
            case ExprOp.ABS:
                return np.abs(self.eval_expr(expr["input"], data))
            case ExprOp.NEG:
                return -self.eval_expr(expr["input"], data)
            case ExprOp.SQRT:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return np.sqrt(np.maximum(x, 0.0))
            case ExprOp.SQUARE:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return x**2
            case ExprOp.ROLLING_MEAN:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return self.rolling_mean(x, int(expr["window"]))
            case ExprOp.RELATIVE_DEVIATION:
                left = np.asarray(self.eval_expr(expr["left"], data), dtype=float)
                right = np.asarray(self.eval_expr(expr["right"], data), dtype=float)
                return np.abs(left - right) / np.maximum(np.abs(right), 1e-12)
            case ExprOp.MAX:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return float(np.max(x))
            case ExprOp.MIN:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return float(np.min(x))
            case ExprOp.MEAN:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return float(np.mean(x))
            case ExprOp.STD:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return float(np.std(x, ddof=int(expr.get("ddof", 0))))
            case ExprOp.RMS:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return float(np.sqrt(np.mean(x**2)))
            case ExprOp.INTEGRAL:
                y = np.asarray(self.eval_expr(expr["input"], data), dtype=float)

                if "x" in expr:
                    x = np.asarray(self.eval_expr(expr["x"], data), dtype=float)
                elif "time_signal" in expr:
                    time_variable = self.parse_variable(expr["time_signal"])
                    x = np.asarray(time_variable.get_value(data), dtype=float)
                else:
                    raise ValueError("INTEGRAL requires 'x' or 'time_signal'.")

                if len(x) != len(y):
                    raise ValueError("Integral x and y must have same length.")

                return float(np.trapz(y, x))
            case ExprOp.PERCENTILE:
                x = np.asarray(self.eval_expr(expr["input"], data), dtype=float)
                return float(np.percentile(x, float(expr["q"])))
            case ExprOp.FIRST_INDEX_WHERE:
                condition = np.asarray(
                    self.eval_condition(expr["condition"], data), dtype=bool
                )
                idx = np.flatnonzero(condition)
                if len(idx) == 0:
                    raise ValueError("No index satisfies FIRST_INDEX_WHERE.")
                return int(idx[0])
            case ExprOp.LAST_INDEX_WHERE:
                condition = np.asarray(
                    self.eval_condition(expr["condition"], data), dtype=bool
                )
                idx = np.flatnonzero(condition)
                if len(idx) == 0:
                    raise ValueError("No index satisfies LAST_INDEX_WHERE.")
                return int(idx[-1])
            case ExprOp.VALUE_AT_INDEX:
                series = np.asarray(self.eval_expr(expr["series"], data), dtype=float)
                index = int(self.eval_expr(expr["index"], data))
                if index < 0 or index >= len(series):
                    raise IndexError(
                        f"Index {index} out of bounds for series length {len(series)}."
                    )
                return float(series[index])
            case ExprOp.INTERP_AT_X:
                x_series = np.asarray(self.eval_expr(expr["x_series"], data), dtype=float)
                y_series = np.asarray(self.eval_expr(expr["y_series"], data), dtype=float)
                x_value = float(self.eval_expr(expr["x_value"], data))

                if len(x_series) != len(y_series):
                    raise ValueError("x_series and y_series must have same length.")

                return float(np.interp(x_value, x_series, y_series))
            case _:
                raise ValueError(f"Unsupported expression op {op}.")

    def eval_condition(self, expr: dict[str, Any], data: dict[str, Any]) -> np.ndarray:
        op = expr.get("op")
        if isinstance(op, str):
            op = self.parse_condition_op(op)

        left = np.asarray(self.eval_expr(expr["left"], data))
        right = np.asarray(self.eval_expr(expr["right"], data))

        match op:
            case ConditionOp.LT:
                return left < right
            case ConditionOp.LE:
                return left <= right
            case ConditionOp.GT:
                return left > right
            case ConditionOp.GE:
                return left >= right
            case ConditionOp.EQ:
                return np.isclose(left, right)
            case ConditionOp.NE:
                return ~np.isclose(left, right)
            case _:
                raise ValueError(f"Unsupported condition op {op}.")

    def parse_variable(self, value: Any) -> Any:
        if self._is_variable(value):
            return value

        if self.variable_resolver is None:
            raise TypeError(
                f"{self.variable_label.title()} parsing is not configured for "
                f"{type(value)}."
            )

        if not isinstance(value, str):
            raise TypeError(
                f"{self.variable_label.title()} must be str or configured variable, "
                f"got {type(value)}"
            )

        return self.variable_resolver(value)

    @staticmethod
    def parse_expr_op(value: str) -> ExprOp:
        mapping = {
            "add": ExprOp.ADD,
            "sub": ExprOp.SUB,
            "mul": ExprOp.MUL,
            "div": ExprOp.DIV,
            "pow": ExprOp.POW,
            "abs": ExprOp.ABS,
            "neg": ExprOp.NEG,
            "sqrt": ExprOp.SQRT,
            "square": ExprOp.SQUARE,
            "rolling_mean": ExprOp.ROLLING_MEAN,
            "relative_deviation": ExprOp.RELATIVE_DEVIATION,
            "max": ExprOp.MAX,
            "min": ExprOp.MIN,
            "mean": ExprOp.MEAN,
            "std": ExprOp.STD,
            "rms": ExprOp.RMS,
            "integral": ExprOp.INTEGRAL,
            "percentile": ExprOp.PERCENTILE,
            "first_index_where": ExprOp.FIRST_INDEX_WHERE,
            "last_index_where": ExprOp.LAST_INDEX_WHERE,
            "value_at_index": ExprOp.VALUE_AT_INDEX,
            "interp_at_x": ExprOp.INTERP_AT_X,
        }
        try:
            return mapping[value]
        except KeyError as exc:
            raise ValueError(f"Unsupported expression op string '{value}'.") from exc

    @staticmethod
    def parse_condition_op(value: str) -> ConditionOp:
        mapping = {
            "lt": ConditionOp.LT,
            "le": ConditionOp.LE,
            "gt": ConditionOp.GT,
            "ge": ConditionOp.GE,
            "eq": ConditionOp.EQ,
            "ne": ConditionOp.NE,
        }
        try:
            return mapping[value]
        except KeyError as exc:
            raise ValueError(f"Unsupported condition op string '{value}'.") from exc

    @staticmethod
    def rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
        if window <= 0:
            raise ValueError("Rolling mean window must be positive.")
        if window > len(x):
            raise ValueError(
                f"Rolling mean window {window} cannot exceed signal length {len(x)}."
            )

        kernel = np.ones(window, dtype=float) / window
        return np.convolve(x, kernel, mode="same")

    def _is_variable(self, value: Any) -> bool:
        return bool(self.variable_types) and isinstance(value, self.variable_types)
