from __future__ import annotations


def test_imports() -> None:
    import hope_discovery
    from hope_discovery import agent, demo, runner

    assert hope_discovery.__doc__
    assert callable(demo.seed) and callable(runner.run_discovery) and agent.DiscoveryAgent
