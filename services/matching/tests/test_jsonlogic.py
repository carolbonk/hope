import pytest
from hope_matching.jsonlogic import JsonLogicError, evaluate, validate

DATA = {"a": {"b": 3}, "tags": ["x", "y"], "s": "2027-01-01", "items": [1, 2, 3]}


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ({"var": "a.b"}, 3),
        ({"var": ["missing", 7]}, 7),
        ({"var": "tags.1"}, "y"),
        ({"==": [{"var": "a.b"}, 3]}, True),
        ({"==": ["3", 3]}, False),
        ({"!=": [1, 2]}, True),
        ({"and": [True, {"var": "a.b"}]}, 3),
        ({"or": [False, 0, "z"]}, "z"),
        ({"!": [[]]}, True),
        ({"!!": [{"var": "tags"}]}, True),
        ({"<": [1, 2, 3]}, True),
        ({">=": [{"var": "s"}, "2026-12-31"]}, True),
        ({"in": ["x", {"var": "tags"}]}, True),
        ({"in": ["ell", "hello"]}, True),
        ({"if": [False, 1, True, 2, 3]}, 2),
        ({"if": [False, 1, 3]}, 3),
        ({"+": [1, 2, 3]}, 6),
        ({"-": [5]}, -5),
        ({"*": [2, 4]}, 8),
        ({"/": [9, 3]}, 3),
        ({"%": [7, 3]}, 1),
        ({"max": [1, 9, 4]}, 9),
        ({"cat": ["a", 1]}, "a1"),
        ({"missing": ["a.b", "nope"]}, ["nope"]),
        ({"missing_some": [1, ["a.b", "nope"]]}, []),
        ({"map": [{"var": "items"}, {"*": [{"var": ""}, 2]}]}, [2, 4, 6]),
        ({"filter": [{"var": "items"}, {">": [{"var": ""}, 1]}]}, [2, 3]),
        ({"all": [{"var": "items"}, {">": [{"var": ""}, 0]}]}, True),
        ({"all": [[], True]}, False),
        ({"some": [{"var": "items"}, {"==": [{"var": ""}, 2]}]}, True),
        ({"none": [{"var": "items"}, {"==": [{"var": ""}, 9]}]}, True),
        ({"merge": [[1], 2, [3]]}, [1, 2, 3]),
    ],
)
def test_operations(rule: object, expected: object) -> None:
    assert evaluate(rule, DATA) == expected


@pytest.mark.parametrize(
    "rule",
    [
        {"eval": ["1+1"]},
        {"a": 1, "b": 2},
        {"+": ["1", 2]},
        {"<": [1, "2"]},
        {"/": [1, 0]},
        {"<": [1]},
    ],
)
def test_rejects_unsafe_or_coercing_rules(rule: object) -> None:
    with pytest.raises(JsonLogicError):
        evaluate(rule, DATA)


def test_depth_limit() -> None:
    rule: object = True
    for _ in range(40):
        rule = {"!": [rule]}
    with pytest.raises(JsonLogicError):
        evaluate(rule)
    with pytest.raises(JsonLogicError):
        validate(rule)


def test_validate_returns_variables() -> None:
    assert validate({"and": [{"var": "a.b"}, {"in": ["x", {"var": ["tags", []]}]}]}) == {
        "a.b",
        "tags",
    }
    with pytest.raises(JsonLogicError):
        validate({"var": [{"var": "dynamic"}]})
    with pytest.raises(JsonLogicError):
        validate({"exec": []})
