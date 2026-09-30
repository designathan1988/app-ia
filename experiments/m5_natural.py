"""Probe: free Portuguese requests over a small page, each on the same starting document.

Not a benchmark with a gate (the phrasings are mine): it shows which mechanisms are missing. Every request is
undone after it runs, so all start from the same page. Runs below normal priority.
Usage: python experiments/m5_natural.py
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.assistant import Assistant  # noqa: E402
from nucleo.builder.client import Builder  # noqa: E402
from nucleo.session import low_priority  # noqa: E402

SETUP = [
    "insira uma seção na página e depois renomeie a seção para Topo",
    'insira um título com o texto "Café Aurora" na seção Topo',
    'insira um parágrafo com o texto "Torrado toda semana." depois do título',
    'insira um botão com o texto "Assinar" no fim da seção Topo',
]

PEDIDOS = [
    "coloque o titulo a direita",
    "alinhe o parágrafo à esquerda",
    "deixe o título em itálico",
    "coloque o texto do botão em maiúsculas",
    "sublinhe o título",
    "deixe o parágrafo em negrito",
    "esconda o botão",
    "oculte o parágrafo",
    "deixe o fundo da seção azul",
    "pinte o título de vermelho",
    "mude a fonte do título para 32px",
    "aumente o tamanho da fonte do título para 40px",
    "coloque uma borda no botão",
    "tire o botão",
    "remova o parágrafo",
    "duplique o botão",
    "centralize o texto da seção",
    "mude o texto do botão para Comprar",
    "troque o texto do título por Café Serra",
    "deixe a seção com fundo preto e o título branco",
    "coloque o botão antes do parágrafo",
    "mova o título para o fim da seção",
    "deixe o parágrafo justificado",
    "coloque o título em caixa alta",
    "arredonde os cantos do botão",
]

if __name__ == "__main__":
    import tempfile

    from nucleo.lang import preferences

    low_priority()
    # every request is undone to restore the page: that must not teach the system that the user rejected it
    scratch = pathlib.Path(tempfile.mkdtemp())
    preferences.STORE = scratch / "preferencias.json"
    t0 = time.time()
    counts: dict[str, int] = {}
    with Builder() as b:
        a = Assistant(b)
        for s in SETUP:
            r = a.handle(s)
            assert r.ok and r.kind == "executado", (s, r.text)
        for p in PEDIDOS:
            t = time.time()
            r = a.handle(p)
            counts[r.kind] = counts.get(r.kind, 0) + 1
            cmds = ", ".join(c if isinstance(c, str) else str(c) for c in r.commands)
            print(f"[{r.kind}] {p}\n    -> {r.text.splitlines()[0] if r.text else ''} {('| ' + cmds) if cmds else ''}"
                  f" ({time.time() - t:.2f}s)")
            if r.kind == "executado":
                a.handle("desfazer")
    print(counts, f"{time.time() - t0:.0f}s")
