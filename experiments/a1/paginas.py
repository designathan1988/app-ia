"""Pages of the A1 corpus: the builder's own fixtures and two pages built in the builder's document format (a shop
named in Portuguese, a landing page named in English)."""
from __future__ import annotations

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nucleo.builder.scenarios import load_fixture  # noqa: E402
from nucleo.lang.mundo import full_document  # noqa: E402


def _n(id_, type_, name, text=None, children=(), **styles):
    st = {"desktop": {"base": {k.replace("_", "-"): v for k, v in styles.items()}}} if styles else {}
    return {"id": id_, "type": type_, "name": name, "text": text, "styles": st, "children": list(children)}


LOJA = full_document([{"tree": _n("pg", "page", "Página", children=[
    _n("cab", "header", "Cabeçalho", children=[
        _n("menu", "nav", "Menu", children=[
            _n("lk1", "link", "Link Início", "Início"),
            _n("lk2", "link", "Link Produtos", "Produtos")])]),
    _n("dest", "section", "Destaque", children=[
        _n("tit", "heading", "Título", "Ofertas da semana", font_size="32px", color="black"),
        _n("sub", "paragraph", "Subtítulo", "Descontos em todo o site"),
        _n("bt1", "button", "Botão", "Comprar agora", width="120px", padding_left="12px"),
        _n("ban", "image", "Banner", width="600px")]),
    _n("pai", "aside", "Painel", width="300px", children=[
        _n("ftit", "heading", "Título 2", "Filtros"),
        _n("fpar", "paragraph", "Parágrafo", "Escolha a categoria")]),
    _n("prod", "section", "Produtos", children=[
        _n("c1", "article", "Cartão 1", margin_left="8px", padding_top="12px", width="240px", children=[
            _n("c1t", "heading", "Título 3", "Café"),
            _n("c1p", "paragraph", "Preço 1", "R$ 20"),
            _n("c1b", "button", "Botão 2", "Adicionar", width="100px")]),
        _n("c2", "article", "Cartão 2", margin_left="8px", width="240px", children=[
            _n("c2t", "heading", "Título 4", "Chá"),
            _n("c2p", "paragraph", "Preço 2", "R$ 15"),
            _n("c2b", "button", "Botão 3", "Adicionar ao carrinho", width="100px")])]),
    _n("rod", "footer", "Rodapé", children=[
        _n("rtx", "paragraph", "Contato", "Fale conosco")])])}])

LANDING = full_document([{"tree": _n("pg", "page", "Page", children=[
    _n("hd", "header", "Header", children=[
        _n("nv", "nav", "Nav", children=[
            _n("hl1", "link", "Home link", "Home"),
            _n("hl2", "link", "Pricing link", "Pricing")])]),
    _n("hero", "section", "Hero", children=[
        _n("ht", "heading", "Headline", "Build faster", font_size="32px"),
        _n("hp", "paragraph", "Lead", "Ship your site today"),
        _n("b1", "button", "Primary", "Get started", width="140px", padding_left="16px"),
        _n("b2", "button", "Secondary", "Learn more", width="140px"),
        _n("im", "image", "Hero image", width="600px")]),
    _n("side", "aside", "Sidebar", width="280px", children=[
        _n("stt", "heading", "Sidebar title", "Updates"),
        _n("stp", "paragraph", "Sidebar text", "New features every week")]),
    _n("feat", "section", "Features", children=[
        _n("fl", "list", "Feature list", children=[
            _n("f1", "listItem", "Feature 1", children=[_n("f1t", "paragraph", "Feature 1 text", "Fast")]),
            _n("f2", "listItem", "Feature 2", children=[_n("f2t", "paragraph", "Feature 2 text", "Secure")]),
            _n("f3", "listItem", "Feature 3", children=[_n("f3t", "paragraph", "Feature 3 text", "Simple")])])]),
    _n("ft", "footer", "Footer", children=[
        _n("cp", "paragraph", "Copyright", "© 2026 Landing")])])}])

PAGES = {"L": LOJA, "E": LANDING, "A": load_fixture("aurora"), "C": load_fixture("catalog"),
         "G": load_fixture("grid-page"), "T": load_fixture("table")}
