"""Audit CLI routing and profiling, without importing real evaluation corpora."""

import sys
from types import SimpleNamespace

import pytest

from experiments.a1 import auditoria as audit


def test_feature_kind_classification_keeps_the_lexical_weight_check(monkeypatch):
    from nucleo.lang import acoes_ranker

    monkeypatch.setattr(audit, "_natural", lambda word: word in {"lit", "probe"})
    monkeypatch.setattr(acoes_ranker, "INIT", {("lit",): 1.0, ("probe",): 2.0})
    assert audit.check_init() == [("probe",)]


def test_gate_cli_delegates_to_one_complete_evaluation(monkeypatch):
    calls = []
    previous_argv = sys.argv

    def run(path, *, run_name):
        calls.append((path, run_name, list(sys.argv)))
        return {"completed": True}

    def forbidden():
        pytest.fail("gate must not run a second standalone audit pipeline")

    monkeypatch.setattr(audit.runpy, "run_path", run)
    monkeypatch.setattr(audit, "run_pipeline", forbidden)
    result = audit.main(["--portao", "2", "--sem-ablacao"])

    evaluator = str(audit.HERE / "avaliar.py")
    assert calls == [(evaluator, "__main__", [evaluator, "2", "--sem-ablacao"])]
    assert result == {"completed": True}
    assert sys.argv is previous_argv


def test_default_cli_stays_on_development_pipeline(monkeypatch):
    calls = []
    profiler = object()
    counts = {"TRAIN": 2, "DEV": 1}

    def forbidden(*args, **kwargs):
        pytest.fail("default audit must not launch the complete evaluator")

    def pipeline():
        calls.append("pipeline")
        return profiler, counts

    def write(observed, *, scope, dataset_counts):
        calls.append((observed, scope, dataset_counts))
        return {"scope": scope}

    monkeypatch.setattr(audit.runpy, "run_path", forbidden)
    monkeypatch.setattr(audit, "run_pipeline", pipeline)
    monkeypatch.setattr(audit, "write_report", write)
    monkeypatch.setitem(sys.modules, "runtime", SimpleNamespace(lower_priority=lambda: calls.append("priority")))

    assert audit.main([]) == {"scope": "development"}
    assert calls == ["priority", "pipeline", (profiler, "development", counts)]


def test_gate_cli_rejects_development_evaluation(monkeypatch):
    calls = []
    monkeypatch.setattr(audit.runpy, "run_path", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(SystemExit) as error:
        audit.main(["--portao", "--dev"])
    assert error.value.code == 2
    assert calls == []


def test_profiler_records_functions_and_counts_only_top_level_generation():
    # Exercise real call frames with an artificial module, no corpus or models.
    namespace = {"__name__": "nucleo.lang.acoes_ranker"}
    exec(compile("def helper():\n    return 1\n\n"
                 "def generate(_segment=False):\n"
                 "    helper()\n"
                 "    if not _segment:\n"
                 "        generate(True)\n", "<audit-probe>", "exec"), namespace)
    previous = sys.getprofile()
    profiler = audit.Profiler()
    profiler.start()
    try:
        namespace["generate"]()
        namespace["generate"]()
    finally:
        profiler.stop()

    assert sys.getprofile() == previous
    assert profiler.generate_calls == 2
    assert {(module, name) for module, name, _ in profiler.executed} == {
        ("nucleo.lang.acoes_ranker", "helper"),
        ("nucleo.lang.acoes_ranker", "generate"),
    }
    namespace["generate"]()
    assert profiler.generate_calls == 2
