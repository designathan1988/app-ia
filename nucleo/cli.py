"""Talk to builder-6 in Portuguese from a terminal.

    python -m nucleo.cli [documento.json] [--saida=pasta] [--codigo=projeto-typescript]

Each line is a request ("insira um título com o texto "Oi" na seção Hero"), a definition ("centralizar significa
definir o alinhamento do texto como center", "card significa um artigo com um título e um botão"), or one of:

    salvar            write the document (also done after every change, when a file was given)
    exportar          write the site (HTML/CSS/JS) into the output folder
    esquecer <termo>  forget a taught word
    desfazer          go back to the state before the last change
    pesquise <termo>  search: MDN, Stack Overflow, the local web-platform reference, npm, GitHub, Wikipedia
    leia <url>        the readable text of a page
    sair

A sentence with "entidade ..." generates a verified TypeScript + Python project. With --codigo, questions about that
TypeScript project are answered too. Two requests joined by "e (depois)" are carried out together or not at all.
Runs below normal priority. The document is the builder's own format (DocumentJson), so it opens in builder-6.

The same answers are available in the browser: python -m nucleo.web_ui
"""

from __future__ import annotations

import json
import pathlib
import sys

from .assistant import Assistant
from .builder.client import Builder
from .session import low_priority


def main(argv: list[str]) -> int:
    low_priority()
    args = [a for a in argv if not a.startswith("--")]
    out = pathlib.Path(next((a.split("=", 1)[1] for a in argv if a.startswith("--saida=")), "site"))
    doc_path = pathlib.Path(args[0]) if args else None
    document = json.loads(doc_path.read_text(encoding="utf-8")) if doc_path and doc_path.exists() else None
    code_root = next((a.split("=", 1)[1] for a in argv if a.startswith("--codigo=")), None)
    with Builder() as b:
        assistant = Assistant(b, document, doc_path, out, code_root)
        print("Pronto. Escreva um pedido (ou 'sair').", flush=True)
        for line in sys.stdin:
            text = line.strip()
            if text == "sair":
                break
            if not text:
                continue
            r = assistant.handle(text)
            mark = {"executado": "✔", "aprendido": "✎", "busca": "", "codigo": "", "projeto": "",
                    "comando": ""}.get(r.kind, "?")
            body = r.text.replace("\n", "\n  ")
            print(f"  {mark} {body}".rstrip() if mark else f"  {body}", flush=True)
            for title, url, _src in r.links:
                print(f"      {url}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
