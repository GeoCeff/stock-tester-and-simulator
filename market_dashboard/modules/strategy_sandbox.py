"""Restricted execution helpers for Quant Lab user strategies."""

from __future__ import annotations

import ast
import multiprocessing as mp
import queue
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd


class StrategyValidationError(ValueError):
    """Raised when user strategy code fails static validation."""


class StrategyExecutionError(RuntimeError):
    """Raised when user strategy code fails during restricted execution."""


@dataclass(frozen=True)
class StrategySandboxResult:
    """Output from a restricted strategy execution."""

    output: Any
    elapsed_seconds: float
    rows_used: int


SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "sum": sum,
    "zip": zip,
}

FORBIDDEN_NAMES = {
    "__builtins__",
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "exit",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "quit",
    "setattr",
    "type",
    "vars",
}

FORBIDDEN_ATTRS = {
    "__class__",
    "__dict__",
    "__globals__",
    "__mro__",
    "__subclasses__",
    "eval",
    "execute",
    "pipe",
    "plot",
    "query",
    "read_clipboard",
    "read_csv",
    "read_excel",
    "read_feather",
    "read_hdf",
    "read_json",
    "read_orc",
    "read_parquet",
    "read_pickle",
    "read_sql",
    "read_table",
    "to_clipboard",
    "to_csv",
    "to_excel",
    "to_feather",
    "to_gbq",
    "to_hdf",
    "to_json",
    "to_latex",
    "to_markdown",
    "to_orc",
    "to_parquet",
    "to_pickle",
    "to_sql",
}

FORBIDDEN_NODES = (
    ast.AsyncFor,
    ast.AsyncFunctionDef,
    ast.AsyncWith,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
)

MAX_CODE_CHARS = 8_000


def validate_strategy_code(code: str) -> None:
    """Validate that code defines exactly one safe `strategy(data)` function."""
    if not isinstance(code, str) or not code.strip():
        raise StrategyValidationError("Strategy code is empty.")
    if len(code) > MAX_CODE_CHARS:
        raise StrategyValidationError("Strategy code is too long for Quant Lab V1.")

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise StrategyValidationError(f"Syntax error on line {exc.lineno}: {exc.msg}.") from exc

    function_defs = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(function_defs) != 1 or function_defs[0].name != "strategy":
        raise StrategyValidationError("Define exactly one function named strategy(data).")

    strategy_fn = function_defs[0]
    if strategy_fn.decorator_list:
        raise StrategyValidationError("Decorators are not allowed on strategy(data).")

    args = strategy_fn.args
    has_one_arg = (
        len(args.args) == 1
        and args.args[0].arg == "data"
        and not args.vararg
        and not args.kwarg
        and not args.kwonlyargs
        and not args.defaults
    )
    if not has_one_arg:
        raise StrategyValidationError("strategy must accept exactly one argument named data.")

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise StrategyValidationError("Import statements are not allowed in Quant Lab strategies.")
            if not (
                isinstance(node, ast.Expr)
                and isinstance(getattr(node, "value", None), ast.Constant)
                and isinstance(node.value.value, str)
            ):
                raise StrategyValidationError("Only strategy(data) may be defined at the top level.")

    has_return = False
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            raise StrategyValidationError(f"{type(node).__name__} is not allowed in Quant Lab strategies.")

        if isinstance(node, ast.Name):
            if node.id.startswith("__") or node.id in FORBIDDEN_NAMES:
                raise StrategyValidationError(f"Use of '{node.id}' is not allowed.")

        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr in FORBIDDEN_ATTRS:
                raise StrategyValidationError(f"Attribute '{node.attr}' is not allowed.")

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_NAMES:
                raise StrategyValidationError(f"Call to '{func.id}' is not allowed.")
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRS:
                raise StrategyValidationError(f"Call to '{func.attr}' is not allowed.")

        if isinstance(node, ast.Return):
            has_return = True

    if not has_return:
        raise StrategyValidationError("strategy(data) must return buy/sell signals or a position Series.")


def _execute_in_worker(code: str, data: pd.DataFrame, result_queue) -> None:
    """Execute strategy code in a child process and return a picklable result."""
    try:
        validate_strategy_code(code)
        namespace: dict[str, Any] = {}
        safe_globals = {"__builtins__": SAFE_BUILTINS}
        compiled = compile(code, "<quant_lab_strategy>", "exec")
        exec(compiled, safe_globals, namespace)
        output = namespace["strategy"](data.copy(deep=True))
        result_queue.put(("ok", output))
    except Exception as exc:
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def execute_strategy_code(
    code: str,
    data: pd.DataFrame,
    timeout_seconds: float = 2.0,
    max_rows: int = 1_500,
) -> StrategySandboxResult:
    """Validate and execute user strategy code with a hard process timeout."""
    validate_strategy_code(code)

    if not isinstance(data, pd.DataFrame) or data.empty:
        raise StrategyExecutionError("Strategy data is empty.")

    rows_used = min(len(data), int(max_rows))
    limited_data = data.tail(rows_used).copy(deep=True)

    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(target=_execute_in_worker, args=(code, limited_data, result_queue))

    start = time.monotonic()
    process.start()
    process.join(timeout_seconds)
    elapsed = time.monotonic() - start

    if process.is_alive():
        process.terminate()
        process.join(1)
        raise StrategyExecutionError("Strategy execution timed out. Use vectorized pandas operations and avoid long loops.")

    try:
        status, payload = result_queue.get_nowait()
    except queue.Empty as exc:
        raise StrategyExecutionError("Strategy execution ended without returning a result.") from exc

    if status != "ok":
        raise StrategyExecutionError(payload)

    return StrategySandboxResult(output=payload, elapsed_seconds=elapsed, rows_used=rows_used)
