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
| **Mundo do código (M3):** resolução de nomes por regras sobre fatos só sintáticos (TypeScript e Python), cadeias de importação e exportação, "todas as referências", impacto, exportações não usadas, incremental por arquivo | julgado pelos compiladores (checker e language service do TS, `symtable` do CPython): **100% de precisão e cobertura** em ~630 mil usos de 6 corpora; validação limpa em 229 mil usos de site-packages; `tests/test_code_world.py` | feito — **portão M3** ([docs/experimentos.md](docs/experimentos.md)) |
| **APIs e web (M4):** diferenças de API entre versões por regras; buscador sem chave que obedece robots.txt (RFC 9309), sem contornar desafios; registros npm/PyPI; alegações → verificação → **aprovação do usuário** → conhecimento | `experiments/m4_api_diff.py`: **99,98%** de acordo com o compilador em 35 pares de versões reais; `experiments/m4_packages.py`: 0 pacotes inexistentes sugeridos, 0 violações de robots.txt; `tests/test_web.py` | feito — **portão M4** (SearXNG pendente: instalação) |
| **Português → ação no builder (M5):** análise sintática linear treinada nos treebanks UD (X2: LAS 80,1 no Porttinari), léxico ancorado no catálogo do builder, verbos dos comandos do builder, nomes de valores CSS em português (Wiktionary, MDN pt-BR), abdução ponderada, restrições executadas pelo planejador; pergunta em vez de chutar | `experiments/m5_requests.py`: **top-1 91,6%, erro silencioso 0,0%**; nomes inventados 92,5%; frases novas 91,1%; frases livres (`m5_natural.py`) 18/25 executadas, nenhuma errada; julgado pelo `matchDocument` do builder; `tests/test_understand.py` | feito — **portão M5** |
| **Ensinar palavras em português (M8, início):** "centralizar significa definir o alinhamento do texto como center", "cor de fundo significa fundo"; aprendido só se a definição for entendida; gravado com origem e data; pode ser esquecido | `tests/test_learned.py`; `experiments/demo_pagina.py` (página montada do zero por pedidos, exportada em HTML/CSS) | feito |
| **Síntese de expressões (M6, parcial):** reconstruir corpos de funções pequenas a partir de exemplos | `experiments/m6_synthesis.py`: 57% numa amostra de 63 tarefas reais, com testes que distinguem; prior contado sem ganho nesta amostra | parcial |
| **Modelo → projeto TypeScript + Python de vários arquivos (M6):** tipos, validadores, repositório com integridade referencial e testes, nas duas linguagens | `experiments/m6_multifile.py`: **30/30 projetos verificados** (tsc estrito, testes, 9.000 valores sem divergência entre TS, Python e referência); defeitos injetados detectados; `tests/test_generation.py` | feito (domínio fixo: dados e validação) |
| **Perguntas sobre código em português:** onde está definido, quem usa, o que é afetado, exportações não usadas | `tests/test_code_questions.py`; sobre a resolução que bate 100% com o `findReferences` do TypeScript | feito |
| **Reparo de defeitos (M7):** templates de correção, julgados em entradas nunca vistas | `experiments/m7_repair.py`: 91,5% em defeitos do tipo dos templates; **32,7% fora deles**; sobreajuste ≤ 1,9% | feito (expressões; sem benchmark externo) |
| **Compreensão do português (viabilidade, X1):** morfologia exata cobre 97,3% das palavras do catálogo humano do builder; a gramática aberta GF do português analisa 89,6% dos 584 rótulos, sem regra de domínio | `experiments/x1_lexico.py`, `experiments/x1_gf.py`, [docs/experimentos.md](docs/experimentos.md) | viabilidade demonstrada; não é ainda compreensão de pedidos |
| **Agregados** (`#count`, `#sum`, `#min`, `#max`), com limite PRESUMIDO quando agregam mundo aberto | campanha só de agregados: 200 mundos iguais ao clingo e ao oráculo ingênuo; exemplos 41–45 | feito |
| **Regras derrotáveis** (`<~`): fatos vencem, prioridade explícita, especificidade, derrota por equipe; INDETERMINADO quando não há vencedor | 200 mundos contra o oráculo ingênuo (decisão própria) e o checador independente; exemplos 46–50 (Tweety, diamante de Nixon) | feito |
| **Conjunto mínimo de conflito** de cada CONTRADITORIO, com a garantia declarada (irredundante; minimal por inclusão quando monótono) | `tests/test_conflict.py`: 439 contradições conferidas pelo oráculo ingênuo, 307 por força bruta sobre todos os subconjuntos | feito |
| **Contextos** (microteorias): herança, isolamento entre irmãos, origem de cada fato e regra | `tests/test_contexts.py`: programa repartido numa cadeia = programa inteiro; cada ancestral vê só a sua parte | feito |
| **Versões em SQLite:** log de transações, `as_of(t)`, tudo ou nada | `tests/test_store.py`: todo estado passado reconstruído, também depois de reabrir o arquivo | feito |
| **Manutenção incremental** pelo cone de dependência, por tupla (DRed) nos componentes sem agregado | `tests/test_incremental.py`: igual à recomputação (átomos, custos, INDETERMINADOS) em sequências aleatórias; ~78% dos componentes reaproveitados; dois defeitos injetados foram detectados | feito — **portão M1** |

## Usar

### No navegador

```
C:\ctv\n\Scripts\python.exe C:\Codex-Shared\nucleo\run_web.py --codigo=C:/Codex-Shared/deepseek/builder-6
```

Abra http://localhost:8790. A tela tem a conversa à esquerda, a pré-visualização da página à direita, exemplos
clicáveis e botões para desfazer, exportar e baixar o documento. Cada pedido leva de ~0,05 a 0,4 s. A primeira pergunta
sobre código lê o projeto uma vez (~20 s).

### No terminal

Conversar com o builder-6 em português, sobre um documento seu (ou um novo):

```
C:\ctv\n\Scripts\python.exe -m nucleo.cli meu-projeto.json --saida=site
```

Exemplos de pedidos:
- `insira uma seção na página`
- `insira um título com o texto "Café Aurora" na seção Topo`
- `defina o fundo da seção Topo como #1e293b`
- `mude a cor do texto do botão para #22d3ee ao passar o mouse`
- `defina o display da seção Topo como flex no celular`

Para ensinar uma palavra: `centralizar significa definir o alinhamento do texto como center`.

Dois pedidos na mesma frase ("insira uma seção na página e depois renomeie a seção para Topo") são feitos juntos,
ou nenhum é feito.

Com `--codigo=C:/Codex-Shared/deepseek/builder-6`, ele também responde perguntas sobre o código TypeScript:
`onde está definido createStore?`, `quem usa validateDocument?`, `o que é afetado se eu mudar siteFiles?`,
`quais exportações não são usadas?`.

Comandos do terminal: `desfazer`, `salvar`, `exportar`, `esquecer <termo>`, `sair`.

O documento é salvo no formato do próprio builder-6 a cada mudança. O que não for entendido é perguntado, nunca
executado.

## Rodar

```
py -m venv C:\ctv\n
C:\ctv\n\Scripts\python.exe -m pip install pytest hypothesis clingo
C:\ctv\n\Scripts\python.exe -m nucleo.lang.morph        # índice do MorphoBr (uma vez)
C:\ctv\n\Scripts\python.exe experiments\x2_parser.py 10  # treina etiquetador e analisador (~13 min)
C:\ctv\n\Scripts\python.exe -m nucleo.lang.values     # nomes em português dos valores CSS (Wiktionary, MDN pt-BR, catálogo; uma vez)
# dicionário e grafo de conceitos: baixar uma vez para data\dicionario\ o pt-extract.jsonl.gz (kaikki.org),
# o own-pt.tar.gz extraído (OpenWordNet-PT) e o english-wordnet-2024.xml.gz (Open English WordNet); ver docs\semantica.md
C:\ctv\n\Scripts\python.exe -m nucleo.lang.dictionary  # definições, sinônimos e traduções (~6 s)
C:\ctv\n\Scripts\python.exe -m nucleo.lang.concepts    # palavras -> conceitos (ILI) -> entidades da máquina (~8 s)
C:\ctv\n\Scripts\python.exe scripts\ci.py
```
