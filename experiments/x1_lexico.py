"""X1a — lexical coverage of builder-6's own pt-BR vocabulary by open morphological data.

Question: can the words people use for the builder be analyzed exactly (lemma + part of speech + features) from
open data, without anyone writing word lists?

Sources, none written by us:

* Test text: builder-6's pt-BR catalogue (src/i18n/locales/pt-BR.json), written by the builder's authors. The
  labels used are those of commands, palette entries, elements and properties, plus the glossary terms.
* Open-class morphology: MorphoBr (form -> lemma+POS+features).
* Closed-class words (articles, prepositions, contractions, pronouns): observed in the UD Portuguese treebanks
  (Porttinari, PetroGold, Bosque), with UPOS and features. Nothing is typed by hand.

Output: coverage numbers, the unknown words, and data/cache/lexico_catalogo.json (the extracted lexicon, keyed by
form, each with its analyses and the catalogue concepts that use it).
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys
import time
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BUILDER = pathlib.Path(r"C:\Codex-Shared\deepseek\builder-6")
PREFIXES = ("command.", "palette.entry.", "element.", "property.")


def words(text: str) -> list[str]:
    """Split on non-letters using Unicode categories (no regex over meaning; just character classes)."""
    out, cur = [], []
    for ch in text:
        if unicodedata.category(ch).startswith("L") or (ch == "-" and cur):
            cur.append(ch.lower())
        else:
            if cur:
                out.append("".join(cur).strip("-"))
                cur = []
    if cur:
        out.append("".join(cur).strip("-"))
    return [w for w in out if w]


def catalogue() -> dict[str, str]:
    cat = json.loads((BUILDER / "src/i18n/locales/pt-BR.json").read_text(encoding="utf-8"))
    labels = {k: v for k, v in cat.items() if k.startswith(PREFIXES) and isinstance(v, str) and "{" not in v}
    glossary = json.loads((BUILDER / "src/i18n/glossary.json").read_text(encoding="utf-8"))
    for c in glossary.get("concepts", []):
        term = c.get("terms", {}).get("pt-BR")
        if term:
            labels[f"glossary.{c['id']}"] = term
    return labels


def ud_closed_class() -> dict[str, collections.Counter]:
    closed = {"ADP", "DET", "PRON", "CCONJ", "SCONJ", "AUX", "PART", "NUM"}
    lex: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for tb in DATA.glob("ud-*"):
        for f in tb.glob("*.conllu"):
            multi: dict = {}
            for line in f.open(encoding="utf-8"):
                if not line.strip() or line.startswith("#"):
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 6:
                    continue
                tid, form, lemma, upos, feats = cols[0], cols[1].lower(), cols[2].lower(), cols[3], cols[5]
                if "-" in tid:  # multiword token (contraction "da" = de + a): remember its span
                    lo, hi = tid.split("-")
                    multi = {"form": form, "lo": int(lo), "hi": int(hi), "parts": []}
                    continue
                if "." in tid:
                    continue
                if multi and multi["lo"] <= int(tid) <= multi["hi"]:
                    multi["parts"].append(f"{lemma}+{upos}+{feats}")
                    if int(tid) == multi["hi"]:
                        lex[multi["form"]]["CONTRACAO:" + " & ".join(multi["parts"])] += 1
                        multi = {}
                    continue
                if upos in closed:
                    lex[form][f"{lemma}+{upos}+{feats}"] += 1
    return lex


def morphobr(needed: set[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = collections.defaultdict(list)
    for folder in ("verbs", "nouns", "adjectives", "adverbs"):
        for f in sorted((DATA / "morphobr" / folder).glob("*.dict")):
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    form, _, analysis = line.rstrip("\n").partition("\t")
                    if form in needed:
                        found[form].append(analysis)
    return found


def main() -> int:
    t0 = time.time()
    labels = catalogue()
    uses: dict[str, set[str]] = collections.defaultdict(set)
    for key, text in labels.items():
        for w in words(text):
            uses[w].add(key)
    tokens = sum(len(words(t)) for t in labels.values())
    closed = ud_closed_class()
    open_found = morphobr(set(uses))
    lexicon = {}
    unknown = []
    for w in sorted(uses):
        analyses = list(open_found.get(w, []))
        if w in closed:
            analyses += [a for a, _ in closed[w].most_common(3)]
        if not analyses and "-" in w:  # compounding: every part analyzable -> compound (general morphology)
            parts = w.split("-")
            part_found = morphobr(set(parts)) if parts else {}
            if all(part_found.get(p) or p in closed for p in parts):
                analyses = ["COMPOSTO:" + " & ".join((part_found.get(p) or [closed[p].most_common(1)[0][0]])[0] for p in parts)]
        if analyses:
            lexicon[w] = {"analises": analyses, "conceitos": sorted(uses[w])}
        else:
            unknown.append(w)
    covered_tokens = sum(len(uses[w]) for w in lexicon)
    all_uses = sum(len(v) for v in uses.values())
    report = {
        "rotulos": len(labels),
        "tokens": tokens,
        "tipos": len(uses),
        "tipos_analisados": len(lexicon),
        "cobertura_tipos": round(len(lexicon) / len(uses), 4),
        "cobertura_ocorrencias": round(covered_tokens / all_uses, 4),
        "desconhecidas": unknown,
        "segundos": round(time.time() - t0, 1),
    }
    out = DATA / "cache"
    out.mkdir(parents=True, exist_ok=True)
    (out / "lexico_catalogo.json").write_text(json.dumps(lexicon, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "x1a_relatorio.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "desconhecidas"}, ensure_ascii=False))
    print("desconhecidas:", " ".join(unknown))
    return 0


if __name__ == "__main__":
    sys.exit(main())
