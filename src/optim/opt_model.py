
# -*- coding: utf-8 -*-
from typing import Any, Hashable, Iterable

import pyoptinterface as poi
from pyoptinterface import gurobi


VariableKey = tuple[str, Hashable]


class OptModel:
    """Lightweight optimization model wrapper.

    The wrapper owns the solver model, variable groups, constraints,
    constraint expressions, and objective expression. Member modules can
    register variables and constraints directly on this object.
    """

    def __init__(self, model_name: str = "model", solver: str = "GUROBI"):
        self.name = model_name
        self.vars: dict[str, dict[Any, Any]] = {}
        self.cons: dict[str, Any] = {}
        self.cons_expr: dict[str, Any] = {}
        self.obj = poi.ExprBuilder()

        if solver != "GUROBI":
            raise ValueError("Only GUROBI is supported by the lightweight OptModel")
        self.model = gurobi.Model()

    def add_var_group(
        self,
        group_name: str,
        keys: Iterable[Any],
        **kwargs: Any,
    ) -> dict[Any, Any]:
        variables = self.model.add_variables(keys, **kwargs)
        self.vars[group_name] = variables
        return variables

    def get_var(self, group_name: str, key: Any) -> Any:
        if group_name not in self.vars:
            raise KeyError(f"Missing variable group: {group_name}")
        try:
            return self.vars[group_name][key]
        except KeyError as exc:
            raise KeyError(f"Missing variable {group_name}: {key}") from exc

    def add_linear_constraint(
        self,
        constraint_key: str,
        expr: Any,
        sense: Any,
        rhs: float,
        name: str,
    ) -> Any:
        constraint = self.model.add_linear_constraint(expr, sense, rhs, name=name)
        self.cons[constraint_key] = constraint
        self.cons_expr[constraint_key] = expr
        return constraint

    def set_objective(self, expr: Any, sense: Any) -> None:
        self.obj = expr
        self.model.set_objective(expr, sense)

    def optimize(self) -> None:
        self.model.optimize()

    def get_value(self, variable: Any) -> float:
        return self.model.get_value(variable)

    def get_model_attribute(self, attribute: Any) -> Any:
        return self.model.get_model_attribute(attribute)
