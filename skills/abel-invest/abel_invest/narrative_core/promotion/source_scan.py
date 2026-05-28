"""Source-level observations for hosted paper promotion.

These helpers intentionally expose best-effort AST observations. They should
not be treated as complete semantic proof that a strategy is stateless or
stateful; the promotion agent still owns source understanding.
"""

from __future__ import annotations

import ast
import re
import sys
from typing import Any


PROMOTION_ALLOWED_RUNTIME_IMPORTS = {
    "abel_edge",
    "numpy",
    "pandas",
}
PROMOTION_FILE_READ_FUNCTIONS = {
    "open",
    "pd.read_csv",
    "pd.read_json",
    "pd.read_parquet",
    "pd.read_pickle",
    "pandas.read_csv",
    "pandas.read_json",
    "pandas.read_parquet",
    "pandas.read_pickle",
    "np.load",
    "numpy.load",
    "joblib.load",
    "pickle.load",
}
PROMOTION_FILE_WRITE_FUNCTIONS = {
    "Path.write_text",
    "Path.write_bytes",
    "np.save",
    "numpy.save",
    "joblib.dump",
    "pickle.dump",
}

TRAINING_CALL_LEAF_NAMES = {
    "calibrate",
    "fit",
    "fit_transform",
    "partial_fit",
    "refit",
    "retrain",
    "train",
    "update_model",
}
TEMPORAL_CONSTANT_NAME_PARTS = (
    "bars",
    "calendar",
    "horizon",
    "lag",
    "lookback",
    "min",
    "period",
    "refit",
    "retrain",
    "row",
    "shift",
    "train",
    "window",
)
TEMPORAL_KEYWORD_NAMES = {
    "alpha",
    "halflife",
    "lag",
    "limit",
    "lookback",
    "min_periods",
    "min_rows",
    "periods",
    "refit_every",
    "span",
    "train_window",
    "window",
    "windows",
}
TEMPORAL_CALL_SUFFIXES = (
    ".bfill",
    ".cummax",
    ".cummin",
    ".cumprod",
    ".cumsum",
    ".ewm",
    ".expanding",
    ".ffill",
    ".pct_change",
    ".quantile",
    ".rank",
    ".rolling",
    ".shift",
)
FINITE_HISTORY_CALL_KINDS = {
    "pct_change",
    "rolling",
    "shift",
}
ORIGIN_ANCHORED_HISTORY_CALL_KINDS = {
    "cummax",
    "cummin",
    "cumprod",
    "cumsum",
    "ewm",
    "expanding",
    "rank",
}
FULL_RUNTIME_COMPUTE_CALL_LEAF_NAMES = {
    "compute_decisions",
    "compute_runtime_output",
    "compute_signals",
    "get_latest_signal",
}


def source_overrides_get_paper_signal(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "get_paper_signal"
            for item in node.body
        ):
            return True
    return False


def paper_signal_design_facts(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _empty_design_facts()
    function = find_function(tree, "get_paper_signal")
    if function is None:
        return {
            "trainingCalls": [],
            "sourceTrainingCalls": training_call_facts(tree),
            "usesStateDir": False,
            "writesState": False,
        }
    return {
        "trainingCalls": training_call_facts(function),
        "sourceTrainingCalls": training_call_facts(tree),
        "usesStateDir": function_uses_state_dir(function),
        "writesState": function_writes_state_like_files(function, tree),
    }


def paper_signal_uses_full_runtime_compute(source: str) -> bool:
    return bool(paper_signal_full_runtime_compute_path(source))


def paper_signal_full_runtime_compute_path(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    top_level_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    paper_class: ast.ClassDef | None = None
    paper_function: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level_functions[node.name] = node
        if not isinstance(node, ast.ClassDef):
            continue
        class_functions = {
            item.name: item
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        function = class_functions.get("get_paper_signal")
        if function is None:
            continue
        paper_class = node
        paper_function = function
        break
    if paper_class is None or paper_function is None:
        return []
    class_functions = {
        item.name: item
        for item in paper_class.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def call_path(
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        label: str,
        path: list[str],
        visited: set[str],
    ) -> list[str]:
        if label in visited:
            return []
        visited = {*visited, label}
        for child in ast.walk(function):
            if not isinstance(child, ast.Call):
                continue
            callee = call_name(child.func)
            leaf = callee.rsplit(".", 1)[-1]
            if leaf in FULL_RUNTIME_COMPUTE_CALL_LEAF_NAMES:
                return [*path, label, leaf]
            helper = None
            helper_label = ""
            if callee.startswith("self."):
                helper_name = callee.rsplit(".", 1)[-1]
                helper = class_functions.get(helper_name)
                helper_label = f"{paper_class.name}.{helper_name}"
            elif "." not in callee:
                helper = top_level_functions.get(callee)
                helper_label = callee
            if helper is None or not helper_label:
                continue
            found = call_path(helper, helper_label, [*path, label], visited)
            if found:
                return found
        return []

    return call_path(
        paper_function,
        f"{paper_class.name}.get_paper_signal",
        [],
        set(),
    )


def source_import_facts(tree: ast.AST | None) -> list[dict[str, str]]:
    if tree is None:
        return []
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = _top_level_module(alias.name)
                if module:
                    modules.add(module)
        elif isinstance(node, ast.ImportFrom):
            module = _top_level_module(node.module or "")
            if module:
                modules.add(module)
    return [
        {"module": module, "classification": _import_classification(module)}
        for module in sorted(modules)
    ]


def source_file_access_facts(tree: ast.AST | None) -> list[dict[str, Any]]:
    if tree is None:
        return []
    constants = _string_constants(tree)
    facts: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        access = _file_access_kind(name)
        if access is None:
            continue
        path_value = ""
        if node.args:
            path_value = _string_expr_value(node.args[0], constants)
        facts.append(
            {
                "function": name,
                "access": access,
                "path": path_value,
                "line": getattr(node, "lineno", 0),
            }
        )
    return facts


def source_temporal_dependency_facts(source: str, tree: ast.AST | None) -> dict[str, Any]:
    if tree is None:
        return {
            "lookbackHints": [],
            "calendarHints": [],
            "parameterHints": [],
            "constantHints": [],
        }
    lookback_hints: list[dict[str, Any]] = []
    calendar_hints: list[dict[str, Any]] = []
    parameter_hints: list[dict[str, Any]] = []
    constant_hints: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()

    def append_unique(collection: list[dict[str, Any]], item: dict[str, Any]) -> None:
        key = (_clean(item.get("kind")), _clean(item.get("expression")), int(item.get("line") or 0))
        if key in seen:
            return
        seen.add(key)
        collection.append(item)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _literal_or_tuple_display(node.value)
            if value is not None:
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    lowered_name = target.id.lower()
                    if not any(part in lowered_name for part in TEMPORAL_CONSTANT_NAME_PARTS):
                        continue
                    append_unique(
                        constant_hints,
                        {
                            "name": target.id,
                            "value": value,
                            "line": getattr(node, "lineno", 0),
                            "kind": "constant",
                            "expression": target.id,
                        },
                    )
        if isinstance(node, ast.Call):
            name = call_name(node.func)
            lowered_call = name.lower()
            if lowered_call in {"range"} or lowered_call.endswith(".range"):
                append_unique(
                    calendar_hints,
                    {
                        "kind": "rangeLoop",
                        "expression": _source_segment(source, node),
                        "line": getattr(node, "lineno", 0),
                    },
                )
            if lowered_call in {
                "bfill",
                "cummax",
                "cummin",
                "cumprod",
                "cumsum",
                "ewm",
                "expanding",
                "ffill",
                "pct_change",
                "quantile",
                "rank",
                "rolling",
                "shift",
            } or lowered_call.endswith(TEMPORAL_CALL_SUFFIXES):
                append_unique(
                    lookback_hints,
                    {
                        "kind": lowered_call.rsplit(".", 1)[-1],
                        "expression": _source_segment(source, node),
                        "line": getattr(node, "lineno", 0),
                    },
                )
            for keyword in node.keywords:
                if keyword.arg not in TEMPORAL_KEYWORD_NAMES:
                    continue
                value = _literal_or_tuple_display(keyword.value) or _source_segment(
                    source, keyword.value
                )
                append_unique(
                    parameter_hints,
                    {
                        "kind": "parameter",
                        "name": keyword.arg,
                        "value": value,
                        "expression": f"{keyword.arg}={value}",
                        "line": getattr(keyword, "lineno", getattr(node, "lineno", 0)),
                    },
                )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            expression = _source_segment(source, node)
            if expression:
                append_unique(
                    calendar_hints,
                    {
                        "kind": "moduloOrdinal",
                        "expression": expression,
                        "line": getattr(node, "lineno", 0),
                    },
                )
        if isinstance(node, ast.Attribute) and node.attr == "iloc":
            append_unique(
                calendar_hints,
                {
                    "kind": "positionalIndexing",
                    "expression": _source_segment(source, node),
                    "line": getattr(node, "lineno", 0),
                },
            )

    return {
        "lookbackHints": lookback_hints[:40],
        "calendarHints": calendar_hints[:40],
        "parameterHints": parameter_hints[:40],
        "constantHints": constant_hints[:40],
        "historyBoundaryCandidates": history_boundary_candidates(
            lookback_hints=lookback_hints,
            calendar_hints=calendar_hints,
            parameter_hints=parameter_hints,
            constant_hints=constant_hints,
        ),
        "interpretation": (
            "Facts only. The agent decides the temporal dependency contract; "
            "calendar hints such as range/modulo/iloc often mean row-index "
            "chronology must be anchored to the selected backtest window."
        ),
    }


def history_boundary_candidates(
    *,
    lookback_hints: list[dict[str, Any]],
    calendar_hints: list[dict[str, Any]],
    parameter_hints: list[dict[str, Any]],
    constant_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return candidate facts, not a final paper history boundary."""

    finite_evidence = [
        _history_hint_label(item)
        for item in lookback_hints
        if _clean(item.get("kind")) in FINITE_HISTORY_CALL_KINDS
    ]
    origin_risks = [
        _history_hint_label(item)
        for item in lookback_hints
        if _clean(item.get("kind")) in ORIGIN_ANCHORED_HISTORY_CALL_KINDS
    ]
    origin_risks.extend(_history_hint_label(item) for item in calendar_hints)
    suggested_bars = _suggested_finite_history_bars(parameter_hints, constant_hints)
    fixed_candidate = bool(finite_evidence) and not origin_risks
    return {
        "fixedLookback": {
            "candidate": fixed_candidate,
            "confidence": "medium" if fixed_candidate else "low",
            "suggestedBars": suggested_bars if fixed_candidate else None,
            "evidence": finite_evidence[:12],
            "risks": origin_risks[:12],
            "note": (
                "Candidate facts only. Choose fixed_lookback only after source "
                "reading confirms the signal depends on finite recent history."
            ),
        },
        "originAnchored": {
            "candidate": True,
            "evidence": origin_risks[:12],
            "reason": (
                "Use when source semantics depend on expanding/cumulative/ranked "
                "history, absolute row ordinals, fitted calendars, or when finite "
                "history is not established by source reading."
            ),
        },
    }


def _history_hint_label(item: dict[str, Any]) -> str:
    kind = _clean(item.get("kind")) or "hint"
    expression = _clean(item.get("expression"))
    line = item.get("line")
    suffix = f" line {line}" if line else ""
    return f"{kind}: {expression}{suffix}" if expression else f"{kind}{suffix}"


def _suggested_finite_history_bars(
    parameter_hints: list[dict[str, Any]],
    constant_hints: list[dict[str, Any]],
) -> int | None:
    numbers: list[int] = []
    for item in [*parameter_hints, *constant_hints]:
        name = _clean(item.get("name")).lower()
        expression = _clean(item.get("expression")).lower()
        if not any(part in f"{name} {expression}" for part in TEMPORAL_CONSTANT_NAME_PARTS):
            continue
        number = _positive_int_from_text(_clean(item.get("value")))
        if number is not None:
            numbers.append(number)
    return max(numbers) if numbers else None


def _positive_int_from_text(value: str) -> int | None:
    matches = re.findall(r"\d+", value)
    if not matches:
        return None
    number = max(int(item) for item in matches)
    return number if number > 0 else None


def source_scan_observations(
    source: str,
    tree: ast.AST | None,
    *,
    file_accesses: list[dict[str, Any]],
) -> dict[str, Any]:
    temporal = source_temporal_dependency_facts(source, tree)
    observed_fit_calls = training_call_facts(tree) if tree is not None else []
    observed_state_writes = [
        item
        for item in file_accesses
        if isinstance(item, dict) and item.get("access") == "write"
    ]
    return {
        "coverage": "best_effort_static_ast",
        "positiveFindings": {
            "observedFitCalls": observed_fit_calls,
            "observedStateWriteCalls": observed_state_writes,
            "observedLookbackOps": temporal.get("lookbackHints", []),
            "observedCalendarOps": temporal.get("calendarHints", []),
        },
        "unprovenAbsences": [
            "No observed fit/train call does not prove absence.",
            "No observed state write does not prove statelessness.",
            "Static scan does not replace source reading by the agent.",
        ],
        "agentDuty": (
            "Inspect source and report semantic dependencies the static scan missed."
        ),
    }


def training_call_facts(function: ast.AST | None) -> list[str]:
    if function is None:
        return []
    calls: list[str] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        callee = call_name(node.func)
        leaf = callee.rsplit(".", 1)[-1].lower()
        if leaf in TRAINING_CALL_LEAF_NAMES and callee not in calls:
            calls.append(callee)
    return calls[:20]


def function_uses_state_dir(function: ast.AST) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            callee = call_name(node.func)
            if callee == "context_runtime_paths" or callee.endswith(
                ".context_runtime_paths"
            ):
                return True
        if isinstance(node, ast.Attribute) and node.attr in {"state_dir", "state"}:
            return True
        if isinstance(node, ast.Constant) and node.value == "_runtime_paths":
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "state_dir" in node.value or "/state/" in node.value:
                return True
    return False


def function_writes_state_like_files(
    function: ast.AST,
    tree: ast.AST | None = None,
    *,
    _visited: set[str] | None = None,
) -> bool:
    helper_functions: dict[str, ast.AST] = {}
    if tree is not None:
        helper_functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
    visited = _visited or set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        callee = call_name(node.func)
        if callee in PROMOTION_FILE_WRITE_FUNCTIONS or callee.endswith(
            (".write_text", ".write_bytes")
        ):
            return True
        lowered = callee.lower()
        if ("write" in lowered or "save" in lowered or "dump" in lowered) and (
            "state" in lowered
            or "checkpoint" in lowered
            or "model" in lowered
            or "scaler" in lowered
        ):
            return True
        helper_name = callee.rsplit(".", 1)[-1]
        helper = helper_functions.get(helper_name)
        if helper is not None and helper_name not in visited:
            visited.add(helper_name)
            if function_writes_state_like_files(helper, tree, _visited=visited):
                return True
    return False


def find_function(
    tree: ast.AST,
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
    return None


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return call_name(node.func)
    return ""


def _empty_design_facts() -> dict[str, Any]:
    return {
        "trainingCalls": [],
        "sourceTrainingCalls": [],
        "usesStateDir": False,
        "writesState": False,
    }


def _top_level_module(value: str) -> str:
    return str(value or "").split(".", 1)[0].strip()


def _import_classification(module: str) -> str:
    if module == "__future__" or module in sys.stdlib_module_names:
        return "stdlib"
    if module in PROMOTION_ALLOWED_RUNTIME_IMPORTS:
        return "allowed_runtime"
    return "nonstandard"


def _file_access_kind(name: str) -> str | None:
    if (
        name in PROMOTION_FILE_READ_FUNCTIONS
        or name in {"read_text", "read_bytes"}
        or name.endswith(".read_text")
        or name.endswith(".read_bytes")
    ):
        return "read"
    if (
        name in PROMOTION_FILE_WRITE_FUNCTIONS
        or name in {"write_text", "write_bytes"}
        or name.endswith(".write_text")
        or name.endswith(".write_bytes")
    ):
        return "write"
    return None


def _literal_or_tuple_display(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return repr(node.value) if isinstance(node.value, str) else str(node.value)
    if isinstance(node, (ast.Tuple, ast.List)):
        values: list[str] = []
        for item in node.elts:
            item_value = _literal_or_tuple_display(item)
            if item_value is None:
                return None
            values.append(item_value)
        opener, closer = ("(", ")") if isinstance(node, ast.Tuple) else ("[", "]")
        return f"{opener}{', '.join(values)}{closer}"
    return None


def _source_segment(source: str, node: ast.AST) -> str:
    try:
        segment = ast.get_source_segment(source, node)
    except Exception:
        segment = None
    if segment:
        return " ".join(segment.strip().split())
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _string_expr_value(node: ast.AST, constants: dict[str, str]) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id, "")
    return ""


def _string_constants(tree: ast.AST) -> dict[str, str]:
    values: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = node.value.value
    return values


def _clean(value: Any) -> str:
    return str(value or "").strip()
