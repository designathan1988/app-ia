# Núcleo

Motor cognitivo **sem LLM** para programação. A inteligência vem de conhecimento
explícito, raciocínio com prova, busca, aprendizado estrutural e verificação.

- Plano aprovado: [docs/plano.md](docs/plano.md)
- Registro da pesquisa (90+ técnicas, com fontes): [docs/pesquisa.md](docs/pesquisa.md)
- Semântica formal com exemplos executáveis: [docs/semantica.md](docs/semantica.md)
- Achados (defeitos descobertos, com evidência): [docs/achados.md](docs/achados.md)
- Experimentos (perguntas de desenho respondidas com medição): [docs/experimentos.md](docs/experimentos.md)

## Estado

**Regra:** nenhuma capacidade é listada aqui sem o teste que a comprova.

| Capacidade | Evidência | Estado |
|---|---|---|
| Linguagem de conhecimento: fatos, regras, negação forte, `not` sobre mundo fechado, `nao_consta` sobre mundo aberto, comparações | `tests/test_analysis.py`, `docs/semantica.md` | feito |
| Admissão: segurança, disciplina de mundo, estratificação com o ciclo exibido | `tests/test_analysis.py` | feito |
| Inferência em várias etapas, com recursão, sobre o modelo perfeito | diferencial contra oráculo ingênuo **e** clingo, 3.000 mundos aleatórios com nomes inventados (`scripts/ci.py`) | feito |
| Status epistêmico: VERDADEIRO / FALSO (afirmado, inferido, presumido, mundo_fechado), CONTRADITORIO, DESCONHECIDO | idem + 48 exemplos calculados à mão | feito |
| Prova de cada conclusão + checador independente (modelo estável: suporte + fechamento) | `tests/test_checker_adversarial.py`: provas e modelos corrompidos são rejeitados | feito |
| Invariância a nomes, à ordem e a conhecimento irrelevante | `tests/test_metamorphic.py` | feito |
| **Ponte sem interface com o builder-6:** store, comandos (256), predicados, manifesto e validador reais, rodando fora do navegador; recusas estruturadas; exportação HTML/CSS | `tests/test_builder_bridge.py`: 450 comandos reais aleatórios, todos os estados válidos pelo validador do próprio builder | feito (F0/X11) |
| **Planejador sobre o builder-6 real (M2):** do estado inicial ao documento esperado de cada cenário do builder, sem ver os passos; efeitos dos comandos aprendidos por experimentação; relevância deduzida pelo núcleo lógico; argumentos abduzidos da diferença | `experiments/m2_plan.py`: **84,7% dos objetivos alcançáveis** (676/798), 78,2% de todos; 800/800 planos confirmados ao refazer do zero; nomes inventados: −0,4 ponto; `tests/test_planner.py` | feito — **portão M2** ([docs/experimentos.md](docs/experimentos.md)) |
| **Compreensão do português (viabilidade, X1):** morfologia exata cobre 97,3% das palavras do catálogo humano do builder; a gramática aberta GF do português analisa 89,6% dos 584 rótulos, sem regra de domínio | `experiments/x1_lexico.py`, `experiments/x1_gf.py`, [docs/experimentos.md](docs/experimentos.md) | viabilidade demonstrada; não é ainda compreensão de pedidos |
| **Agregados** (`#count`, `#sum`, `#min`, `#max`), com limite PRESUMIDO quando agregam mundo aberto | campanha só de agregados: 200 mundos iguais ao clingo e ao oráculo ingênuo; exemplos 41–45 | feito |
| **Regras derrotáveis** (`<~`): fatos vencem, prioridade explícita, especificidade, derrota por equipe; INDETERMINADO quando não há vencedor | 200 mundos contra o oráculo ingênuo (decisão própria) e o checador independente; exemplos 46–50 (Tweety, diamante de Nixon) | feito |
| **Conjunto mínimo de conflito** de cada CONTRADITORIO, com a garantia declarada (irredundante; minimal por inclusão quando monótono) | `tests/test_conflict.py`: 439 contradições conferidas pelo oráculo ingênuo, 307 por força bruta sobre todos os subconjuntos | feito |
| **Contextos** (microteorias): herança, isolamento entre irmãos, origem de cada fato e regra | `tests/test_contexts.py`: programa repartido numa cadeia = programa inteiro; cada ancestral vê só a sua parte | feito |
| **Versões em SQLite:** log de transações, `as_of(t)`, tudo ou nada | `tests/test_store.py`: todo estado passado reconstruído, também depois de reabrir o arquivo | feito |
| **Manutenção incremental** pelo cone de dependência | `tests/test_incremental.py`: igual à recomputação (átomos, custos, INDETERMINADOS) em sequências aleatórias; ~78% dos componentes reaproveitados; dois defeitos injetados foram detectados | feito — **portão M1** |

## Rodar

```
py -m venv C:\ctv\n
C:\ctv\n\Scripts\python.exe -m pip install pytest hypothesis clingo
C:\ctv\n\Scripts\python.exe scripts\ci.py
```
