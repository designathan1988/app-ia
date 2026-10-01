"""One place that answers a message, for the terminal and the web interface alike.

A message is, in this order:
- a command: desfazer, salvar, exportar, esquecer <termo>;
- a page to read: "leia <url>";
- a search: "pesquise ...";
- a project description (it mentions "entidade");
- a question about the code (with a code project);
- otherwise a request or a definition for the builder document.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from dataclasses import dataclass, field

from .builder.client import Builder
from .lang import learned
from .lang.morph import lemmas
from .session import Session

ROOT = pathlib.Path(__file__).resolve().parents[1]


@dataclass
class Reply:
    kind: str  # executado | aprendido | perguntar | nao_entendi | sem_plano | busca | codigo | projeto | comando
    text: str
    ok: bool = True
    commands: list = field(default_factory=list)
    links: list = field(default_factory=list)  # [(title, url, source)]


class Assistant:
    def __init__(self, builder: Builder, document: dict | None = None, doc_path: pathlib.Path | None = None,
                 out: pathlib.Path = pathlib.Path("site"), code_root: str | None = None) -> None:
        self.session = Session(builder, document)
        self.doc_path = doc_path
        self.out = out
        self.code_root = code_root
        self._code_index = None
        self._previous: list[int] = []
        self._fetcher = None

    def warm_up(self) -> None:
        """Load what the first request would otherwise wait for: the language models and the builder."""
        from .lang.interpret import understand_request as understand
        from .lang.understand import World

        doc = self.session.document()
        understand("insira um título na página", World.from_document(doc["document"], doc["selection"]))

    def code_index(self):
        """Built on the first question about code (~20 s once): building it in the background starved the web
        server's requests of CPU."""
        if self._code_index is None:
            from .lang.code_questions import CodeIndex

            index = CodeIndex(self.code_root)
            _ = index.cb.model
            self._code_index = index
        return self._code_index

    def fetcher(self):
        if self._fetcher is None:
            from .web.fetcher import Fetcher

            self._fetcher = Fetcher(ROOT / "data" / "cache" / "web")
        return self._fetcher

    def _save(self) -> None:
        if self.doc_path:
            self.doc_path.write_text(json.dumps(self.session.document()["document"], ensure_ascii=False, indent=1),
                                     encoding="utf-8")

    def undo(self) -> Reply:
        if not self._previous:
            return Reply("comando", "Nada a desfazer.", False)
        self.session.state = self._previous.pop()
        if self.session.last_reading:
            from .lang import preferences

            preferences.undone(*self.session.last_reading)  # evidence against that reading of that verb
            self.session.last_reading = None
        self._save()
        return Reply("comando", "Desfeito.")

    def export(self) -> Reply:
        for f in self.session.export():
            path = self.out / f["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f["text"], encoding="utf-8")
        return Reply("comando", f"Site exportado em {self.out.resolve()}")

    def preview_html(self) -> str:
        """The page as exported, with its CSS inlined (for a preview frame)."""
        files = {f["path"]: f["text"] for f in self.session.export()}
        page = next((t for p, t in files.items() if p.endswith(".html")), "<p>(vazio)</p>")
        css = files.get("css/styles.css", "")
        return page.replace('<link rel="stylesheet" href="css/styles.css">', f"<style>{css}</style>")

    def handle(self, text: str) -> Reply:
        text = text.strip()
        words = text.split()
        if not words:
            return Reply("comando", "", False)
        first = words[0].lower()
        if text == "desfazer":
            return self.undo()
        if text == "exportar":
            return self.export()
        if text == "salvar":
            self._save()
            return Reply("comando", f"Salvo em {self.doc_path}" if self.doc_path else "Sem arquivo para salvar.",
                         bool(self.doc_path))
        if first == "esquecer" and len(words) > 1:
            word = text.split(None, 1)[1]
            return Reply("comando", f"{'Esquecido' if learned.forget(word) else 'Não conheço'}: {word}")
        if first in ("leia", "ler", "abra") and len(words) > 1 and words[1].startswith("http"):
            from .web.search import read_page

            return Reply("busca", read_page(self.fetcher(), words[1]))
        if any(lem in ("pesquisar", "procurar", "buscar") for lem in lemmas(first, "V")):
            from .web.search import search

            query = text.split(None, 1)[1] if len(words) > 1 else ""
            query = query[6:] if query.lower().startswith("sobre ") else query
            hits = search(query, self.fetcher())
            lines = [f"[{h.source}] {h.title} — {h.summary[:140]}" for h in hits[:12]]
            return Reply("busca", "\n".join(lines) or "Nada encontrado.", bool(hits),
                         links=[(h.title, h.url, h.source) for h in hits[:12]])
        if " entidade " in f" {text.lower()} ":
            return self._project(text)
        looks_like_question = text.endswith("?") or first in ("onde", "quem", "quais", "qual", "que", "o")
        if self.code_root and looks_like_question:
            from .lang.code_questions import answer, is_code_question

            index = self.code_index()
            if index is None:
                return Reply("codigo", "Ainda estou lendo o código do projeto; pergunte de novo em alguns segundos.",
                             False)
            if is_code_question(text, index):
                a = answer(text, index)
                return Reply("codigo", a.text, a.kind != "nao_entendi")
        doc = self.session.document()
        from .lang.questions import answer as page_answer
        from .lang.understand import World

        q = page_answer(text, World.from_document(doc["document"], doc["selection"]), doc["document"],
                        self.session.dialog.last_reading)
        if q is not None:
            return Reply("resposta", q.text, True)
        before = self.session.state
        a = self.session.ask(text)
        if a.decision == "executado":
            self._previous.append(before)
            self._save()
        return Reply(a.decision, a.message, a.ok, a.commands)

    def _project(self, text: str) -> Reply:
        from .gen.build import verify
        from .lang.describe_model import DescriptionError, model_from_text

        try:
            model = model_from_text(text)
        except DescriptionError as e:
            return Reply("nao_entendi", str(e), False)
        target = (self.out.parent if self.out.name == "site" else self.out) / "projeto-gerado"
        shutil.rmtree(target, ignore_errors=True)
        r = verify(model, workdir=str(target))
        (target / "modelo.json").write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
        dif = r.get("diferencial", {})
        head = "✔ Projeto verificado" if r["verificado"] else "✘ Projeto NÃO verificado"
        return Reply("projeto", f"{head}: {r['arquivos']} arquivos, {r['linhas']} linhas em {target.resolve()}\n"
                                f"tsc: {len(r['tsc'])} problema(s); testes TS: {r.get('testes_ts')}; testes Python: "
                                f"{r['testes_py']}; diferencial: {dif.get('valores', 0)} valores, "
                                f"{dif.get('divergencias', '?')} divergência(s)", r["verificado"])
