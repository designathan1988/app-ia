"""Legacy graph entities must not consume A1's lexical evidence budget.

Kept outside normal pytest collection until the audit isolation step. This uses
abstract graph output only; no lexical databases, datasets or training are read.
"""

from nucleo.lang import concepts
from nucleo.lang import evidencia as evidence


def test_legacy_action_anchor_does_not_evict_allowed_evidence(monkeypatch):
    allowed = [(('comando', f'unit.op-{i:02d}'), 1.0, ()) for i in range(40)]
    monkeypatch.setattr(concepts, 'meanings', lambda *args, **kwargs: allowed)
    baseline = evidence._from_graph('q', 'en')
    assert len(baseline) == 40

    with_legacy = [(('acao', 'legacy'), 0.0, ())] + allowed
    monkeypatch.setattr(concepts, 'meanings', lambda *args, **kwargs: with_legacy)
    actual = evidence._from_graph('q', 'en')

    # The ignored kind must be removed before applying the budget; otherwise
    # unrelated legacy anchors can alter A1's candidate generation indirectly.
    assert actual == baseline
