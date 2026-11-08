from __future__ import annotations


def test_imports_and_demo_seed_is_a_no_op() -> None:
    import hope_discovery
    from hope_discovery import demo

    assert hope_discovery.__doc__
    assert demo.seed() is None
