"""Latency helper tests without loading datasets, models or the builder."""

import ast
from pathlib import Path
import statistics
from types import SimpleNamespace

import pytest


@pytest.fixture
def latency_namespace():
    # Load just the production helper definitions, not evaluator module imports.
    root = Path(__file__).resolve().parents[1]
    if root.name == "data":  # proposed test is initially under data/cache
        root = root.parent
    source = root / "experiments" / "a1" / "avaliar.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {"pct", "measure_dev_latency"}]
    assert {node.name for node in functions} == {"pct", "measure_dev_latency"}
    namespace = {"statistics": statistics, "sys": SimpleNamespace(getprofile=lambda: None)}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class InferenceInputs:
    def __getitem__(self, index):
        # Reading gold, categories or traversing a whole corpus item is forbidden.
        assert index in (0, 1, 2, 5)
        return {0: "xx", 1: "page", 2: "q", 5: {"ref": "node"}}[index]


def test_latency_times_inference_without_gold_and_preserves_stats(latency_namespace):
    namespace = latency_namespace
    previous = {"gen_secs": [99], "rank_secs": [88], "n": [77]}
    ranker = SimpleNamespace(stats=previous)
    calls = []
    ticks = iter([100.0, 100.006, 200.0, 200.010])
    namespace["time"] = SimpleNamespace(perf_counter=lambda: next(ticks))

    def context(item, sandbox):
        assert item == ("xx", "page", "q", (), "", {"ref": "node"})
        calls.append("context")
        return "page-view", "discourse"

    def interpret(observed, text, lang, page, discourse):
        assert observed is ranker
        assert (text, lang, page, discourse) == ("q", "xx", "page-view", "discourse")
        calls.append("interpret")
        observed.stats["gen_secs"].append(.002)
        observed.stats["rank_secs"].append(.001)
        observed.stats["n"].append(5)

    namespace.update(context=context, interpret=interpret)
    result = namespace["measure_dev_latency"](ranker, [InferenceInputs(), InferenceInputs()], object())
    assert calls == ["context", "interpret", "context", "interpret"]
    assert result == {
        "dataset": "DEV", "n": 2, "warm": True, "profiling_enabled": False,
        "total_ms_mean": 8.0, "total_ms_p95": 10.0,
        "gen_ms_mean": 2.0, "gen_ms_p95": 2.0,
        "rank_ms_mean": 1.0, "rank_ms_p95": 1.0,
    }
    assert ranker.stats is previous
    assert previous == {"gen_secs": [99], "rank_secs": [88], "n": [77]}


def test_latency_rejects_active_profiler_before_inference(latency_namespace):
    namespace = latency_namespace
    namespace["sys"].getprofile = lambda: object()
    previous = {"unchanged": True}
    ranker = SimpleNamespace(stats=previous)
    with pytest.raises(RuntimeError, match="profiler"):
        namespace["measure_dev_latency"](ranker, [InferenceInputs()], object())
    assert ranker.stats is previous


def test_latency_restores_statistics_when_inference_fails(latency_namespace):
    namespace = latency_namespace
    namespace["time"] = SimpleNamespace(perf_counter=lambda: 0)
    namespace["context"] = lambda *args: (None, None)

    def interpret(*args):
        raise ValueError("probe failure")

    namespace["interpret"] = interpret
    previous = {"unchanged": True}
    ranker = SimpleNamespace(stats=previous)
    with pytest.raises(ValueError, match="probe failure"):
        namespace["measure_dev_latency"](ranker, [InferenceInputs()], object())
    assert ranker.stats is previous
