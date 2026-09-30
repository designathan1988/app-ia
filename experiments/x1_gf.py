"""X1b — does the open GF Portuguese resource grammar parse builder-6's own human-written labels?

Pipeline (nothing hand-written about the domain):
1. The lexicon comes from X1a (data/cache/lexico_catalogo.json): MorphoBr analyses of the catalogue's words.
2. We *generate* a GF lexicon module from it: nouns carry their gender from MorphoBr; verbs and adjectives
   use the RGL's smart paradigms (mkV / mkA), which inflect regular words exactly.
3. We compile Catalogo = Lang (the RGL's wide grammar) + that lexicon, and parse every label of commands,
   palette entries, elements and properties as an utterance (Utt).

Measured: the share of labels with at least one parse, the number of parses per label (ambiguity), and the time.
"""

from __future__ import annotations

import collections
import json
import pathlib
import subprocess
import sys
import time
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GF = pathlib.Path(r"C:\ctv\gf\gf.exe")
RGL = DATA / "gf-rgl" / "src"
EXTEND = "--extend" in sys.argv
OUT = DATA / "cache" / ("x1gf_extend" if EXTEND else "x1gf")
EXT_FUNS = "[CompoundN, PastPartAP, ApposNP]"
EXT_ABS = f", Extend{EXT_FUNS}" if EXTEND else ""
EXT_CNC = f", ExtendPor{EXT_FUNS}" if EXTEND else ""
CANARY = "o título"  # a minimal noun phrase every working grammar of this lexicon must parse
sys.path.insert(0, str(ROOT))
from experiments.x1_lexico import catalogue, words  # noqa: E402


def ident(lemma: str, cat: str) -> str:
    base = "".join(c for c in unicodedata.normalize("NFD", lemma) if not unicodedata.combining(c))
    base = "".join(c if c.isalnum() else "_" for c in base)
    return f"w_{base}_{cat}"


def gf_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def morph_tables(lemmas: set[str]) -> dict[tuple[str, str], list[tuple[str, list[str]]]]:
    """All MorphoBr forms of the needed lemmas: (lemma, POS) -> [(form, features)]."""
    tables: dict[tuple[str, str], list] = collections.defaultdict(list)
    for folder in ("verbs", "nouns", "adjectives"):
        for f in sorted((DATA / "morphobr" / folder).glob("*.dict")):
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    form, _, analysis = line.rstrip("\n").partition("\t")
                    lemma, _, rest = analysis.partition("+")
                    if lemma in lemmas:
                        pos, *feats = rest.split("+")
                        tables[(lemma, pos)].append((form, feats))
    return tables


def pick(forms: list[str]) -> str | None:
    return sorted(set(forms))[0] if forms else None  # deterministic; BR "aplicamos" sorts before PT "aplicámos"


def plain(feats) -> bool:
    return not ({"DIM", "AUG", "SUPER", "NEG"} & set(feats))


GF_MODES = {"PRS": ("Pres", "Ind"), "SBJR": ("Pres", "Sub"), "IMPF": ("PretI", "Ind"), "SBJP": ("PretI", "Sub"),
            "FUT": ("Fut", "Ind"), "SBJF": ("Fut", "Sub")}
GF_SIMPLE = {"PQP": "MQPerf", "PRF": "PretP", "COND": "Cond"}


def verb_table(entries) -> str | None:
    by = collections.defaultdict(list)
    for form, feats in entries:
        if plain(feats):
            by[tuple(feats)].append(form)
    inf = pick(by.get(("INF",), []))
    if inf is None:
        return None
    rows = [f'VI Infn => "{inf}"', f'VI Ger => "{pick(by.get(("GRD",), [])) or inf}"',
            f'VI Part => "{pick(by.get(("PTPST", "M", "SG"), [])) or inf}"']
    subj_pres = {(p, n): set(by.get(("SBJR", p, n), [])) for p in "123" for n in ("SG", "PL")}
    for n_gf, n in (("Sg", "SG"), ("Pl", "PL")):
        for p in "123":
            for tag, (tense, mode) in GF_MODES.items():
                f = pick(by.get((tag, p, n), []))
                rows.append(f'VPB ({tense} {mode} {n_gf} P{p}) => ' + (f'"{f}"' if f else "nonExist"))
            for tag, tense in GF_SIMPLE.items():
                f = pick(by.get((tag, p, n), []))
                rows.append(f'VPB ({tense} {n_gf} P{p}) => ' + (f'"{f}"' if f else "nonExist"))
            # affirmative imperative: the IMP form that is not the (negative) subjunctive form
            imp = [x for x in by.get(("IMP", p, n), []) if not (p == "2" and x in subj_pres[(p, n)])]                 or by.get(("IMP", p, n), [])
            f = pick(imp)
            rows.append(f'VPB (Imper {n_gf} P{p}) => ' + (f'"{f}"' if f else "nonExist"))
    return "{s = table {" + " ; ".join(rows) + "}}"


def build_lexicon(lexicon: dict) -> tuple[list[str], list[str]]:
    wanted = set()
    for entry in lexicon.values():
        for a in entry["analises"]:
            if not a.startswith(("CONTRACAO:", "COMPOSTO:")) and "+" in a:
                lemma, pos, *_ = a.split("+")
                if pos in ("N", "A", "V", "ADV"):
                    wanted.add((lemma, pos))
    tables = morph_tables({l for l, _ in wanted})
    funs, lins = [], []
    for lemma, pos in sorted(wanted):
        entries = tables.get((lemma, pos), [])
        if pos == "N":
            genders = {g for _, feats in entries for g in feats if g in ("M", "F")} or {"M", "F"}
            for g in sorted(genders):
                sg = pick([f for f, ft in entries if plain(ft) and "SG" in ft and (g in ft or not {"M", "F"} & set(ft))]) or lemma
                pl = pick([f for f, ft in entries if plain(ft) and "PL" in ft and (g in ft or not {"M", "F"} & set(ft))]) or sg
                name = ident(lemma + ("" if len(genders) == 1 else "_" + g), "N")
                funs.append(f"  {name} : N ;")
                lins.append(f'  {name} = mkN {gf_string(sg)} {gf_string(pl)} {"feminine" if g == "F" else "masculine"} ;')
        elif pos == "A":
            def form(g, n):
                return pick([f for f, ft in entries if plain(ft) and n in ft and (g in ft or not {"M", "F"} & set(ft))])
            ms, fs, mp, fp = form("M", "SG"), form("F", "SG"), form("M", "PL"), form("F", "PL")
            ms = ms or lemma
            fs, mp = fs or ms, mp or ms
            fp = fp or mp
            name = ident(lemma, "A")
            funs.append(f"  {name} : A ;")
            lins.append(f"  {name} = mkA {gf_string(ms)} {gf_string(fs)} {gf_string(mp)} {gf_string(fp)} ;")
        elif pos == "V":
            table = verb_table(entries)
            if table is None:
                continue
            for cat, body in (("V", f"mkV (lin Verbum {table})"), ("V2", f"mkV2 (mkV (lin Verbum {table}))")):
                name = ident(lemma, cat)
                funs.append(f"  {name} : {cat} ;")
                lins.append(f"  {name} = {body} ;")
        elif pos == "ADV":
            name = ident(lemma, "Adv")
            funs.append(f"  {name} : Adv ;")
            lins.append(f"  {name} = mkAdv {gf_string(lemma)} ;")
    return funs, lins


def write_grammar(lexicon: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    funs, lins = build_lexicon(lexicon)
    (OUT / "Catalogo.gf").write_text(
        f"abstract Catalogo = Lang{EXT_ABS} ** {{\nfun\n" + "\n".join(funs) + "\n}\n", encoding="utf-8")
    (OUT / "CatalogoPor.gf").write_text(
        "--# -path=.:" + ":".join(str(RGL / d).replace("\\", "/") for d in
                                   ("prelude", "abstract", "common", "romance", "portuguese", "api")) + "\n"
        f"concrete CatalogoPor of Catalogo = LangPor{EXT_CNC} ** open ParadigmsPor, BeschPor, ParamX, Predef in {{\nflags coding=utf8 ;\nlin\n"
        + "\n".join(lins) + "\n}\n", encoding="utf-8")
    print("léxico gerado:", len(funs), "entradas")


def labels_to_parse() -> dict[str, str]:
    out = {}
    for key, text in catalogue().items():
        if key.startswith("glossary."):
            continue
        if any(not (unicodedata.category(c).startswith("L") or c in " -") for c in text):
            continue  # skip labels with digits, parentheses, symbols
        out[key] = text[0].lower() + text[1:]
    return out


def main() -> int:
    lexicon = json.loads((DATA / "cache" / "lexico_catalogo.json").read_text(encoding="utf-8"))
    write_grammar(lexicon)
    labels = labels_to_parse()
    script = [f"i -retain {(OUT / 'CatalogoPor.gf').as_posix()}", 'ps "@@@ __canario__"', f"p -cat=Utt {gf_string(CANARY)}"]
    for key, text in labels.items():
        script.append(f'ps "@@@ {key}"')
        script.append(f"p -cat=Utt {gf_string(text)}")
    t0 = time.time()
    proc = subprocess.run([str(GF), "--run"], input="\n".join(script) + "\n", capture_output=True,
                          text=True, encoding="utf-8", cwd=OUT, timeout=3600)
    elapsed = time.time() - t0
    parses: dict[str, int] = collections.Counter()
    failures: dict[str, str] = {}
    current = None
    preamble = proc.stdout.split("@@@ ", 1)[0].strip()
    if preamble:
        raise SystemExit("gramática não compilou; medição abortada:\n" + preamble[:1500])
    for line in proc.stdout.splitlines():
        if line.startswith("@@@ "):
            current = line[4:].strip()
            parses[current] = 0
            continue
        if current is None or not line.strip():
            continue
        if line.startswith(("The parser failed", "The sentence is not complete", "Unknown words")):
            failures[current] = line.strip()
        elif line.startswith("Utt"):  # only real abstract syntax trees count as parses
            parses[current] += 1
    if parses.get("__canario__", 0) == 0:
        raise SystemExit("frase-controle não foi analisada; medição inválida")
    parsed = [k for k in labels if parses.get(k, 0) > 0 and k not in failures]
    by_prefix = collections.defaultdict(lambda: [0, 0])
    for k in labels:
        p = k.split(".")[0]
        by_prefix[p][1] += 1
        if k in parsed:
            by_prefix[p][0] += 1
    amb = [parses[k] for k in parsed]
    report = {
        "rotulos": len(labels),
        "analisados": len(parsed),
        "cobertura": round(len(parsed) / max(1, len(labels)), 4),
        "por_tipo": {k: f"{a}/{t}" for k, (a, t) in by_prefix.items()},
        "ambiguidade_mediana": sorted(amb)[len(amb) // 2] if amb else None,
        "ambiguidade_max": max(amb) if amb else None,
        "segundos_total": round(elapsed, 1),
        "exemplos_falha": {k: (labels[k], failures.get(k, "sem análise")) for k in list(set(labels) - set(parsed))[:25]},
        "stderr": proc.stderr[-1500:],
    }
    (OUT / "x1b_relatorio.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("exemplos_falha", "stderr")}, ensure_ascii=False))
    for k, v in list(report["exemplos_falha"].items())[:25]:
        print("  falha:", v[0], "|", v[1][:80])
    if proc.stderr.strip():
        print("stderr:", proc.stderr[-800:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
