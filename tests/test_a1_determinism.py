"""A1 evidence, scoring and short TRAIN runs must not depend on iteration order."""

import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from nucleo.lang import acoes_ranker as ar
from nucleo.lang import concepts
from nucleo.lang import evidencia as ev


def test_score_is_order_independent_and_preserves_float_cancellation():
    ranker = ar.Ranker.__new__(ar.Ranker)
    ranker.w = {("probe", "a"): 1e16, ("probe", "b"): 1.0, ("probe", "c"): -1e16}
    scores = [ranker.score(dict((key, 1.0) for key in order))
              for order in itertools.permutations(ranker.w)]
    assert scores == [1.0] * len(scores)


def test_graph_evidence_cutoff_is_independent_of_tied_anchor_order(monkeypatch):
    # One abstract concept reaches more tied entities than the evidence cap.
    # Keep the real graph traversal, ordering and cutoff under test.
    anchors = [(("valor", (f"p{i:02d}", "v")), 0.0) for i in range(48)]
    monkeypatch.setattr(concepts, "concepts_of", lambda *args: (("c", 0.0),))
    monkeypatch.setattr(concepts, "neighbours", lambda *args: ())
    monkeypatch.setattr(concepts, "_anchors", lambda: {"c": anchors})
    forward = ev._from_graph("probe", "en")
    anchors.reverse()
    backward = ev._from_graph("probe", "en")
    assert len(forward) == len(backward) == 40
    assert forward == backward


_SHORT_TRAIN = textwrap.dedent("""\
    from experiments.a1.runtime import lower_priority
    lower_priority()

    import json
    import os
    from experiments.a1 import avaliar as evaluation
    from nucleo.lang.acoes_ranker import Ranker
    from nucleo.lang.mundo import Sandbox

    # Training uses only TRAIN; optional preflight validates TRAIN/DEV.
    # Importing the evaluator does not run its main gate.
    items = [item for lang in ("pt", "en")
             for item in [row for row in evaluation.TRAIN if row[0] == lang][:8]]
    ranker = Ranker()
    sandbox = Sandbox()
    try:
        if os.environ.get("A1_WARM_DEV") == "1":
            assert not evaluation.preflight(sandbox, dev_only=True)["gold_errors"]
        stats = evaluation.train(ranker, items, 2, sandbox)
    finally:
        sandbox.close()

    snapshot = {
        "stats": stats,
        "weights": [[repr(key), float(value).hex()]
                    for key, value in sorted(ranker.w.items(), key=lambda item: repr(item[0]))],
        "inv": [[repr(key), sorted(repr(atom) for atom in atoms)]
                for key, atoms in sorted(ranker.inv.items(), key=lambda item: repr(item[0]))],
    }
    print(json.dumps(snapshot, sort_keys=True))
    """)


def test_short_train_has_identical_weights_across_hash_seeds():
    root = Path(__file__).resolve().parents[1]
    snapshots = []
    # Blocking runs deliberately keep the expensive jobs sequential.
    # Each child lowers its own priority and closes its bridge in finally.
    for seed, warm in (("1", "0"), ("2", "0"), ("1", "1")):
        env = dict(os.environ, PYTHONHASHSEED=seed, A1_WARM_DEV=warm)
        result = subprocess.run([sys.executable, "-c", _SHORT_TRAIN], cwd=root, env=env,
                                capture_output=True, text=True, encoding="utf-8", check=True)
        snapshots.append(json.loads(result.stdout))

    assert snapshots[0]["stats"]["train_items"] == 16
    for snapshot in snapshots[1:]:
        assert snapshots[0]["stats"] == snapshot["stats"]
        assert snapshots[0]["weights"] == snapshot["weights"]
        assert snapshots[0]["inv"] == snapshot["inv"]
