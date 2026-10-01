"""Automatic audit: is there hand-written intent knowledge in the A1 pipeline?

Method:
1. The pipeline (generate + rank, the analysis of the utterance, the lexical evidence, the grounding) is *run* on
   every utterance of the corpus while a profiler records every function that executes (sys.setprofile).
2. The source of each executed function of the project is inspected:
   - references to the old hand-written linguistic knowledge (language profiles, frames.json and its verb lists,
     FRAME_COMMANDS, STATE_OF_FRAME, the taught vocabulary, MODALS);
   - regular expressions: a pattern containing a literal word of a natural language would be an intent regex;
     patterns made only of character classes (numbers, units, word characters) are structural;
   - literal collections of strings: a list/set/dict of natural-language words is reported with its use;
     a mapping from a word to an operation, property, value or element type would be an intent rule.
3. The initial weights (INIT) are checked to name kinds of evidence only, never a word.
4. Every lexical evidence source is listed with its origin (nucleo/lang/evidencia.py ORIGINS).

Output: data/cache/a1_auditoria.json and a summary (python experiments/a1/auditoria.py).
"""
from __future__ import annotations

import argparse
import ast
import inspect
import json
import pathlib
import re
import runpy
import sys
import textwrap

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

LEGACY = {
    "profile(": "language profile (langs.PROFILES: hand-written word lists)",
    "PROFILES": "language profiles (hand-written word lists)",
    "frames.json": "hand-written frames and verb lists",
    "FRAMES": "hand-written frames and verb lists",
    "_in_frame": "hand-written frames and verb lists",
    "_known_verb": "hand-written frames and verb lists",
    "FRAME_COMMANDS": "hand-written frame -> command map",
    "STATE_OF_FRAME": "hand-written frame -> state map",
    "learned.": "vocabulary taught in conversation (data of the user, not of this project)",
    "MODALS": "hand-written modal verb list",
}
# known literal collections of the executed code and what they are (reviewed by reading the code; anything not
# listed here is reported as UNREVIEWED)
KNOWN = {
    ("nucleo.lang.values", "STOP"): ("estrutural", "function words skipped when indexing MDN descriptions"),
    ("nucleo.lang.values", "GLOBAL"): ("externa", "CSS-wide keywords (W3C), not language"),
    ("nucleo.lang.values", "START"): ("estrutural", "MDN section names (document structure)"),
    ("nucleo.lang.values", "END"): ("estrutural", "MDN section names (document structure)"),
    ("nucleo.lang.concepts", "REL_COST"): ("estrutural", "cost per WordNet relation type (graph search)"),
    ("nucleo.lang.concepts", "GLOSS_SKIP"): ("estrutural", "light verbs skipped when linking glosses; those edges "
                                                          "are not followed (REL_COST has no 'definition')"),
    ("nucleo.lang.concepts", "DIRECTED"): ("estrutural", "relation types followed upward only"),
    ("nucleo.lang.command_verbs", "STRUCTURAL"): ("estrutural", "effect field names of the builder"),
    ("nucleo.lang.morph", "PARTS"): ("externa", "MorphoBr file names"),
    ("nucleo.lang.morph", "ACCENTS"): ("estrutural", "orthography: accented letters"),
    ("nucleo.lang.dictionary", "POS"): ("externa", "Wiktionary part-of-speech names"),
    ("nucleo.lang.acoes_ranker", "SUPPORTED"): ("estrutural", "argument type names of the ActionSchema"),
    ("nucleo.lang.acoes_ranker", "UNITS"): ("externa", "CSS length units (W3C)"),
    ("nucleo.lang.acoes_ranker", "WIDTH"): ("estrutural", "search widths (parameters)"),
    ("nucleo.lang.acoes_ranker", "INIT"): ("estrutural", "initial weights of feature kinds; literal evidence 'lit' "
                                               "is not a word weight; check_init separately audits lexical keys"),
    ("nucleo.lang.ud", "TREEBANKS"): ("externa", "file names of the UD treebanks"),
    ("nucleo.lang.evidencia", "_GRAPH_KIND"): ("estrutural", "internal names of the kinds of schema constants"),
    ("nucleo.lang.langs", "PROFILES"): ("legado", "reached only through langs.use (language registry) and "
                                                  "lexicon._load (the catalog's file name); no word list of it is "
                                                  "read by the A1 pipeline"),
}
# legacy references the profiler shows the pipeline reaches, and why they do not put hand knowledge in A1's output
LEGACY_OK = {
    ("nucleo.lang.concepts", "_anchors", "FRAME_COMMANDS"): "builds anchors of kind 'acao' only; evidencia drops "
                                                             "that kind before its retrieval cap (_GRAPH_KIND); "
                                                             "tests/test_a1_legacy_isolation.py checks noninterference",
    ("nucleo.lang.langs", "use", "PROFILES"): "checks that a language code is known",
    ("nucleo.lang.langs", "profile", "profile("): "called by lexicon._load for the catalog's file name only",
    ("nucleo.lang.langs", "profile", "PROFILES"): "called by lexicon._load for the catalog's file name only",
    ("nucleo.lang.lexicon", "_load", "profile("): "reads profile()['catalog']: the file name pt-BR.json / en.json",
}
CSS_UNITS = {"px", "rem", "em", "vh", "vw", "ms", "deg", "fr"}


class Profiler:
    """Record reached project functions and actual top-level generation calls."""

    def __init__(self):
        self.executed = set()
        self.generate_calls = 0
        self._codes = {}
        self._running = False
        self._previous = None

    def _profile(self, frame, event, arg):
        if event != "call":
            return
        code = frame.f_code
        key = id(code)
        cached = self._codes.get(key)
        # One code object can be reused with another globals namespace. Guard
        # that identity so caching cannot hide a different module's function.
        if cached is None or cached[1] is not frame.f_globals:
            mod = frame.f_globals.get("__name__", "")
            if mod.startswith("nucleo."):
                self.executed.add((mod, code.co_name, code.co_firstlineno))
            is_generate = mod == "nucleo.lang.acoes_ranker" and code.co_name == "generate"
            cached = (code, frame.f_globals, is_generate)
            self._codes[key] = cached
        if cached[2] and not frame.f_locals.get("_segment", False):
            self.generate_calls += 1

    def start(self):
        if self._running:
            raise RuntimeError("audit profiler already running")
        self._previous = sys.getprofile()
        self._running = True
        sys.setprofile(self._profile)

    def stop(self):
        if self._running:
            sys.setprofile(self._previous)
            self._running = False


def run_pipeline():
    from avaliar import DEV, TRAIN, context
    from nucleo.lang.acoes_ranker import Ranker
    from nucleo.lang.mundo import Sandbox

    profiler = Profiler()
    sb = Sandbox()
    try:
        # Audit development paths without consuming the one-shot held-out gate.
        items = TRAIN + DEV
        profiler.start()
        try:
            r = Ranker()
            for it in items:
                pg, disc = context(it, sb)
                cx = r.context(it[2], it[0], pg, disc)
                r.rank(cx, r.generate(cx))
        finally:
            profiler.stop()
    finally:
        sb.close()
    return profiler, {"TRAIN": len(TRAIN), "DEV": len(DEV)}


def _natural(word: str) -> bool:
    from nucleo.lang import langs
    from nucleo.lang.morph import analyses

    w = word.lower()
    if not re.fullmatch(r"[a-zà-ÿ]{3,}", w):
        return False
    try:
        return bool(analyses(w)) or w in langs._english_words()
    except Exception:  # noqa: BLE001
        return False


def inspect_functions(executed) -> dict:
    import importlib

    legacy, regexes, collections_ = [], [], []
    modules = sorted({m for m, _, _ in executed})
    for mod in modules:
        try:
            m = importlib.import_module(mod)
            src = inspect.getsource(m)
        except Exception:  # noqa: BLE001
            continue
        tree = ast.parse(src)
        lines = src.splitlines()
        funcs = {(n.name, n.lineno): n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef,
                                                                                 ast.AsyncFunctionDef))}
        names_used = set()
        for (mm, name, line) in executed:
            if mm != mod:
                continue
            node = funcs.get((name, line)) or next((n for (fn, ln), n in funcs.items() if fn == name), None)
            if node is None:
                continue
            body = "\n".join(lines[node.lineno - 1:node.end_lineno])
            for pat, what in LEGACY.items():
                if pat in body:
                    why = LEGACY_OK.get((mod, name, pat))
                    legacy.append({"module": mod, "function": name, "reference": pat, "what": what,
                                   "class": "legado-sem-efeito" if why else "REGRA MANUAL ALCANÇADA", "why": why})
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name):
                    names_used.add(sub.id)
                if isinstance(sub, ast.Call) and getattr(sub.func, "attr", getattr(sub.func, "id", "")) in (
                        "compile", "findall", "match", "fullmatch", "search", "sub", "split"):
                    if sub.args and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str):
                        pat = sub.args[0].value
                        words = [w for w in re.findall(r"[a-zà-ÿ]{3,}", re.sub(r"\\[a-zA-Z]|\[[^\]]*\]", " ", pat))
                                 if _natural(w) and w not in CSS_UNITS]
                        regexes.append({"module": mod, "function": name, "pattern": pat,
                                        "class": "INTENT REGEX" if words else "estrutural", "words": words})
        # module-level literal collections the executed functions use
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Set, ast.List, ast.Dict, ast.Tuple)):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id in names_used:
                        strs = [c.value for c in ast.walk(node.value) if isinstance(c, ast.Constant) and
                                isinstance(c.value, str)]
                        nat = [s for s in strs if _natural(s)]
                        if len(strs) >= 3:
                            cls, why = KNOWN.get((mod, tgt.id), ("UNREVIEWED", ""))
                            collections_.append({"module": mod, "name": tgt.id, "strings": len(strs),
                                                 "natural_words": nat[:12], "class": cls, "why": why})
        # module-level compiled regexes the executed functions use
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and \
                    getattr(node.value.func, "attr", "") == "compile" and node.value.args and \
                    isinstance(node.value.args[0], ast.Constant):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id in names_used:
                        pat = node.value.args[0].value
                        words = [w for w in re.findall(r"[a-zà-ÿ]{3,}", re.sub(r"\\[a-zA-Z]|\[[^\]]*\]", " ", pat))
                                 if _natural(w) and w not in CSS_UNITS]
                        regexes.append({"module": mod, "name": tgt.id, "pattern": pat,
                                        "class": "INTENT REGEX" if words else "estrutural", "words": words})
    return {"legacy_references": legacy, "regexes": regexes, "literal_collections": collections_,
            "modules": modules}


def check_init() -> list:
    from nucleo.lang.acoes_ranker import INIT

    bad = []
    for k in INIT:
        for part in k:
            if isinstance(part, str) and _natural(part) and part not in (
                    "name", "text", "lit", "catalog", "wordnet", "values", "synonym", "translation", "number", "op",
                    "prop", "value", "type"):
                bad.append(k)
    return bad


def write_report(profiler, *, scope, dataset_counts):
    """Write the audit of the run already observed; never interpret more items."""
    executed = profiler.executed
    found = inspect_functions(executed)
    from nucleo.lang.evidencia import ORIGINS

    intent_rules = [c for c in found["literal_collections"] if c["class"] == "UNREVIEWED" and c["natural_words"]]
    intent_regex = [r for r in found["regexes"] if r["class"] == "INTENT REGEX"]
    report = {
        "scope": scope,
        "dataset_counts": dict(dataset_counts),
        "utterances_run": profiler.generate_calls,
        "top_level_generation_calls": profiler.generate_calls,
        "functions_executed": len(executed),
        "modules_executed": found["modules"],
        "legacy_hand_knowledge_reached": found["legacy_references"],
        "regexes": found["regexes"],
        "literal_collections": found["literal_collections"],
        "init_weights_naming_words": check_init(),
        "evidence_origins": ORIGINS,
        "summary": {
            "handwritten intent rules (unreviewed word lists in executed code)": len(intent_rules),
            "regex intent rules": len(intent_regex),
            "legacy hand knowledge reached with effect": len([x for x in found["legacy_references"]
                                                              if x["class"] != "legado-sem-efeito"]),
            "init weights naming a word": len(check_init()),
        },
    }
    out = ROOT / "data" / "cache" / "a1_auditoria.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=1))
    for x in found["legacy_references"]:
        print("LEGACY", x)
    for x in intent_regex:
        print("REGEX", x)
    for x in found["literal_collections"]:
        print("COLLECTION", x["module"], x["name"], x["class"], x["natural_words"][:6])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portao", action="store_true", help="audit the single complete A1 gate execution")
    args, forwarded = parser.parse_known_args(argv)
    if not args.portao and forwarded:
        parser.error("evaluation arguments require --portao")
    if args.portao:
        if "--dev" in forwarded:
            parser.error("--portao requires the complete evaluation, without --dev")
        # avaliar.py owns the profiler lifecycle for its complete gate. Delegating
        # once preserves dialogue state, training, ablations and honest counts.
        previous = sys.argv
        sys.argv = [str(HERE / "avaliar.py"), *forwarded]
        try:
            return runpy.run_path(str(HERE / "avaliar.py"), run_name="__main__")
        finally:
            sys.argv = previous
    from runtime import lower_priority
    lower_priority()
    profiler, counts = run_pipeline()
    return write_report(profiler, scope="development", dataset_counts=counts)


if __name__ == "__main__":
    main()
