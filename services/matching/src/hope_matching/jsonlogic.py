"""A small, safe JSON Logic evaluator (https://jsonlogic.com). Pure data walking, no eval.

Equality is type-strict (`==` behaves like `===`) and arithmetic only accepts numbers, so a
rule that relies on JavaScript coercion fails loudly instead of passing by accident.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

MAX_DEPTH = 32
MAX_NODES = 2_000

Op = Callable[[Any, Any, int], Any]


class JsonLogicError(ValueError):
    pass


def truthy(value: Any) -> bool:
    return bool(value)


def _number(value: Any) -> float | int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise JsonLogicError(f"expected a number, got {value!r}")
    return value


def _args(raw: Any) -> list[Any]:
    return raw if isinstance(raw, list) else [raw]


def _lookup(data: Any, path: Any, default: Any = None) -> Any:
    if path is None or path == "":
        return data
    current = data
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return default
    return current


def _var(raw: Any, data: Any, depth: int) -> Any:
    args = [evaluate(a, data, depth) for a in _args(raw)]
    return _lookup(data, args[0] if args else None, args[1] if len(args) > 1 else None)


def _missing(raw: Any, data: Any, depth: int) -> list[Any]:
    keys = [evaluate(a, data, depth) for a in _args(raw)]
    if keys and isinstance(keys[0], list):
        keys = keys[0]
    return [k for k in keys if _lookup(data, k) is None]


def _missing_some(raw: Any, data: Any, depth: int) -> list[Any]:
    need, keys = (evaluate(a, data, depth) for a in _args(raw))
    missing = [k for k in keys if _lookup(data, k) is None]
    return missing if len(keys) - len(missing) < need else []


def _if(raw: Any, data: Any, depth: int) -> Any:
    args = _args(raw)
    for i in range(0, len(args) - 1, 2):
        if truthy(evaluate(args[i], data, depth)):
            return evaluate(args[i + 1], data, depth)
    return evaluate(args[-1], data, depth) if len(args) % 2 else None


def _and(raw: Any, data: Any, depth: int) -> Any:
    value: Any = None
    for arg in _args(raw):
        value = evaluate(arg, data, depth)
        if not truthy(value):
            return value
    return value


def _or(raw: Any, data: Any, depth: int) -> Any:
    value: Any = None
    for arg in _args(raw):
        value = evaluate(arg, data, depth)
        if truthy(value):
            return value
    return value


def _evaluated(fn: Callable[[list[Any]], Any]) -> Op:
    def op(raw: Any, data: Any, depth: int) -> Any:
        return fn([evaluate(a, data, depth) for a in _args(raw)])

    return op


def _comparable(a: Any, b: Any) -> None:
    if isinstance(a, str) and isinstance(b, str):
        return
    _number(a)
    _number(b)


def _compare(check: Callable[[Any, Any], bool]) -> Op:
    def op(raw: Any, data: Any, depth: int) -> bool:
        values = [evaluate(a, data, depth) for a in _args(raw)]
        if len(values) not in (2, 3):
            raise JsonLogicError("comparison takes 2 or 3 arguments")
        pairs = list(itertools.pairwise(values))
        for a, b in pairs:
            _comparable(a, b)
        return all(check(a, b) for a, b in pairs)

    return op


def _strict_eq(values: list[Any]) -> bool:
    a, b = values
    return (type(a) is type(b) and a == b) or (_is_num(a) and _is_num(b) and a == b)


def _is_num(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _in(values: list[Any]) -> bool:
    needle, haystack = values
    if isinstance(haystack, str):
        return isinstance(needle, str) and needle in haystack
    if isinstance(haystack, list):
        return any(_strict_eq([needle, item]) for item in haystack)
    return False


def _arith(values: list[Any], op: str) -> float | int:
    nums = [_number(v) for v in values]
    if not nums:
        raise JsonLogicError(f"{op} needs arguments")
    if op == "+":
        return sum(nums)
    if op == "*":
        result: float | int = 1
        for n in nums:
            result *= n
        return result
    if op == "-":
        return -nums[0] if len(nums) == 1 else nums[0] - nums[1]
    if nums[1] == 0:
        raise JsonLogicError("division by zero")
    return nums[0] / nums[1] if op == "/" else nums[0] % nums[1]


def _iterate(kind: str) -> Op:
    def op(raw: Any, data: Any, depth: int) -> Any:
        args = _args(raw)
        items = evaluate(args[0], data, depth)
        if not isinstance(items, list):
            items = []
        rule = args[1] if len(args) > 1 else None
        results = [evaluate(rule, item, depth) for item in items]
        if kind == "map":
            return results
        if kind == "filter":
            return [i for i, r in zip(items, results, strict=True) if truthy(r)]
        if kind == "all":
            return bool(items) and all(truthy(r) for r in results)
        if kind == "some":
            return any(truthy(r) for r in results)
        return not any(truthy(r) for r in results)

    return op


def _merge(values: list[Any]) -> list[Any]:
    out: list[Any] = []
    for v in values:
        out.extend(v if isinstance(v, list) else [v])
    return out


OPERATIONS: dict[str, Op] = {
    "var": _var,
    "missing": _missing,
    "missing_some": _missing_some,
    "if": _if,
    "?:": _if,
    "and": _and,
    "or": _or,
    "==": _evaluated(_strict_eq),
    "===": _evaluated(_strict_eq),
    "!=": _evaluated(lambda v: not _strict_eq(v)),
    "!==": _evaluated(lambda v: not _strict_eq(v)),
    "!": _evaluated(lambda v: not truthy(v[0])),
    "!!": _evaluated(lambda v: truthy(v[0])),
    "<": _compare(lambda a, b: a < b),
    "<=": _compare(lambda a, b: a <= b),
    ">": _compare(lambda a, b: a > b),
    ">=": _compare(lambda a, b: a >= b),
    "in": _evaluated(_in),
    "cat": _evaluated(lambda v: "".join(str(x) for x in v)),
    "max": _evaluated(lambda v: max(_number(x) for x in v)),
    "min": _evaluated(lambda v: min(_number(x) for x in v)),
    "+": _evaluated(lambda v: _arith(v, "+")),
    "-": _evaluated(lambda v: _arith(v, "-")),
    "*": _evaluated(lambda v: _arith(v, "*")),
    "/": _evaluated(lambda v: _arith(v, "/")),
    "%": _evaluated(lambda v: _arith(v, "%")),
    "merge": _evaluated(_merge),
    "map": _iterate("map"),
    "filter": _iterate("filter"),
    "all": _iterate("all"),
    "some": _iterate("some"),
    "none": _iterate("none"),
}


def _operator(rule: Any) -> tuple[str, Any] | None:
    if isinstance(rule, dict) and len(rule) == 1:
        ((name, raw),) = rule.items()
        return str(name), raw
    return None


def evaluate(rule: Any, data: Any = None, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        raise JsonLogicError("rule is nested too deeply")
    if isinstance(rule, list):
        return [evaluate(r, data, depth + 1) for r in rule]
    op = _operator(rule)
    if op is None:
        if isinstance(rule, dict):
            raise JsonLogicError("an operation object must have exactly one key")
        return rule
    name, raw = op
    if name not in OPERATIONS:
        raise JsonLogicError(f"unknown operation {name!r}")
    return OPERATIONS[name](raw, data, depth + 1)


def validate(rule: Any) -> set[str]:
    """Check a rule is well formed and within limits. Returns the `var` paths it reads."""
    variables: set[str] = set()
    count = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise JsonLogicError("rule is too large")
        if isinstance(node, list):
            for child in node:
                walk(child, depth + 1)
            return
        if isinstance(node, dict):
            op = _operator(node)
            if op is None:
                raise JsonLogicError("an operation object must have exactly one key")
            name, raw = op
            if name not in OPERATIONS:
                raise JsonLogicError(f"unknown operation {name!r}")
            if name == "var":
                first = _args(raw)[0] if _args(raw) else ""
                if not isinstance(first, str | int):
                    raise JsonLogicError("var paths must be literals")
                variables.add(str(first))
            walk(raw, depth + 1)
            return
        if not (node is None or isinstance(node, str | int | float | bool)):
            raise JsonLogicError(f"unsupported literal {node!r}")

    walk(rule, 0)
    return variables
