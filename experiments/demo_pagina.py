"""Practical test: build a small page in builder-6 from nothing, with Portuguese requests only, then export it.

Includes requests the system should NOT carry out (unknown verb, ambiguous reference, missing value), to show
what it does then. Runs below normal priority.
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.builder.client import Builder  # noqa: E402
from nucleo.session import Session, low_priority  # noqa: E402

PEDIDOS = [
    "insira uma seção na página",
    "renomeie a seção para Destaque",
    'insira um título com o texto "Bem-vindo à Aurora" na seção Destaque',
    'coloque um parágrafo com o texto "Café torrado toda semana." depois do título',
    'adicione um botão com o texto "Assinar" no fim da seção Destaque',
    "defina o fundo da seção Destaque como #0f172a",
    "mude a cor do texto do título para #ffffff",
    "deixe o padding superior da seção Destaque em 64px",
    "coloque 18px no tamanho da fonte do parágrafo",
    "mude a cor do texto do botão para #22d3ee ao passar o mouse",
    "defina o display da seção Destaque como flex no celular",
    # the system should not carry these out
    "centralize o título",
    "insira um parágrafo na seção Destaque e depois apague o botão",
    "blorfe o botão",
    "defina a margem superior do parágrafo",
    "apague o botão",
]

if __name__ == "__main__":
    low_priority()
    out = pathlib.Path(__file__).resolve().parents[1] / "data" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with Builder() as b:
        s = Session(b)
        for p in PEDIDOS:
            t = time.time()
            a = s.ask(p)
            mark = "OK " if a.ok else "-- "
            print(f"{mark}[{a.decision}] {p}\n      -> {a.message}  {a.commands}  ({time.time() - t:.1f}s)")
        files = s.export()
    for f in files:
        (out / f["path"]).parent.mkdir(parents=True, exist_ok=True)
        (out / f["path"]).write_text(f["text"], encoding="utf-8")
    ok = sum(a.ok for a in s.history)
    print(f"\n{ok}/{len(PEDIDOS)} executados em {time.time() - t0:.0f}s; exportado em {out}")
    for f in files:
        print(f"\n===== {f['path']} =====\n{f['text'][:1500]}")
