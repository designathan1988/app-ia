"""Find the first random world where engine and naive oracle disagree, and show the relevant rules."""
import sys

sys.path.insert(0, ".")
from nucleo.kb.syntax import parse_program  # noqa: E402
from nucleo.logic.engine import evaluate  # noqa: E402
from tests.gen.worlds import random_program  # noqa: E402
from tests.oracle import naive  # noqa: E402

start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
for seed in range(start, start + 2000):
    src = random_program(seed, aggregates=True, defeasible=True)
    prog = parse_program(src)
    model = evaluate(prog)
    ref, ind = naive.perfect_model(prog, with_indeterminate=True)
    if set(model.entries) != ref or model.indeterminate != ind:
        print("seed", seed)
        diff = set(model.entries) ^ ref
        print("diferença:", sorted(map(str, diff)))
        preds = {a.pred.name for a in diff}
        for r in prog.rules:
            if r.head.pred.name in preds:
                print("  regra:", r)
        print("---- programa ----")
        print(src)
        break
else:
    print("nenhuma divergência")
