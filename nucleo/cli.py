"""Talk to builder-6 in Portuguese from a terminal.

    python -m nucleo.cli [documento.json] [--saida=pasta] [--codigo=projeto-typescript]

Each line is a request ("insira um título com o texto "Oi" na seção Hero"), a definition ("centralizar significa
definir o alinhamento do texto como center"), or one of:

    salvar            write the document (also done after every change, when a file was given)
    exportar          write the site (HTML/CSS/JS) into the output folder
    esquecer <termo>  forget a taught word
    desfazer          go back to the state before the last change
    sair

With --codigo, questions about that TypeScript project are answered too: "onde está definido X?", "quem usa X?",
"o que é afetado se eu mudar X?", "quais exportações não são usadas?". Two requests joined by "e (depois)" are
carried out together or not at all.

Runs below normal priority. The document is the builder's own format (DocumentJson), so it opens in builder-6.
"""

from __future__ import annotations

import json
import pathlib
import sys

from .builder.client import Builder
from .lang import learned
from .session import Session, low_priority


def main(argv: list[str]) -> int:
    low_priority()
    args = [a for a in argv if not a.startswith("--")]
    out = pathlib.Path(next((a.split("=", 1)[1] for a in argv if a.startswith("--saida=")), "site"))
    doc_path = pathlib.Path(args[0]) if args else None
    document = json.loads(doc_path.read_text(encoding="utf-8")) if doc_path and doc_path.exists() else None
    code_root = next((a.split("=", 1)[1] for a in argv if a.startswith("--codigo=")), None)
    code_index = None
    with Builder() as b:
        s = Session(b, document)
        previous: list[int] = []
        print("Pronto. Escreva um pedido (ou 'sair').", flush=True)
        for line in sys.stdin:
            text = line.strip()
            if not text:
                continue
            if text == "sair":
                break
            if text == "salvar" or text == "exportar" or text.startswith("esquecer ") or text == "desfazer":
                if text == "desfazer":
                    if previous:
                        s.state = previous.pop()
                        print("  desfeito", flush=True)
                    else:
                        print("  nada a desfazer", flush=True)
                elif text.startswith("esquecer "):
                    word = text[len("esquecer "):].strip()
                    print(f"  {'esquecido' if learned.forget(word) else 'não conheço'}: {word}", flush=True)
                elif text == "exportar":
                    for f in s.export():
                        path = out / f["path"]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(f["text"], encoding="utf-8")
                    print(f"  site exportado em {out.resolve()}", flush=True)
                if doc_path and text in ("salvar", "desfazer"):
                    doc_path.write_text(json.dumps(s.document()["document"], ensure_ascii=False, indent=1),
                                        encoding="utf-8")
                    print(f"  salvo em {doc_path}", flush=True)
                continue
            if code_root:
                from .lang.code_questions import CodeIndex, answer, is_code_question

                if code_index is None:
                    print("  (lendo o código do projeto...)", flush=True)
                    code_index = CodeIndex(code_root)
                if is_code_question(text, code_index):
                    print("  " + answer(text, code_index).text.replace("\n", "\n  "), flush=True)
                    continue
            before = s.state
            a = s.ask(text)
            if a.decision == "executado":
                previous.append(before)
                if doc_path:
                    doc_path.write_text(json.dumps(s.document()["document"], ensure_ascii=False, indent=1),
                                        encoding="utf-8")
            mark = {"executado": "✔", "aprendido": "✎"}.get(a.decision, "?")
            print(f"  {mark} {a.message}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
