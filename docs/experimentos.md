# Experimentos

Cada experimento responde a uma pergunta que decide o desenho. As respostas são **medidas**, com o script que as
reproduz.

## X1 — A gramática aberta do português serve de base para entender pedidos de programação?

**Texto de teste, que não é meu:** o catálogo pt-BR do builder-6 (`src/i18n/locales/pt-BR.json` e `glossary.json`),
escrito pelos autores do builder. São os rótulos de comandos, da paleta, dos elementos e das propriedades: 616 rótulos
e 1.549 palavras.

### X1a — Morfologia exata a partir de dados abertos (`experiments/x1_lexico.py`)

**Fontes:**
- MorphoBr (Apache-2.0) para palavras de classe aberta;
- palavras funcionais **observadas** nos treebanks UD (Porttinari, PetroGold, Bosque), com as contrações vindas dos
  tokens compostos do UD (`às` = a + as);
- compostos com hífen analisados pelas partes.

**Nenhuma lista de palavras foi digitada.**

| Medida | Valor |
|---|---|
| Tipos (palavras distintas) analisados | **429 / 441 = 97,3%** |
| Ocorrências analisadas | **98,1%** |
| Não analisadas | `all canvas css gap html padding svg tag translate url zip` (estrangeirismos, que o glossário do builder define como conceitos) e `mesclagem` (derivação ausente no MorphoBr) |

### X1b — Análise sintática com a gramática GF do português (`experiments/x1_gf.py`)

**O que foi usado:**
- A gramática de recursos GF do português "segue majoritariamente o português brasileiro" (README do gf-rgl).
- O léxico é **gerado** a partir do X1a.
- Cada rótulo é analisado como enunciado (`Utt`).
- **Proteções do medidor:**
  - só contam árvores sintáticas reais;
  - uma frase-controle precisa ser analisada;
  - qualquer erro de compilação aborta a medição.
  - Uma primeira versão sem essas proteções reportou um **falso 100%** quando a gramática não compilava. O defeito foi
    corrigido antes de qualquer conclusão.

| Configuração | Cobertura | Ambiguidade mediana (máx.) | Tempo (584 rótulos) |
|---|---|---|---|
| Léxico por paradigmas "inteligentes" do GF | 489/584 = 83,7% | 3 (249) | 87 s |
| **Léxico com todas as formas exatas do MorphoBr** | **523/584 = 89,6%** | 3 (280) | 40–47 s |

**Achados sobre a gramática aberta:**
1. **Os paradigmas automáticos de flexão do GF para o português erram:**
   - `inferior` gera o feminino "inferiora";
   - `aplicar` é conjugado como "apficar / apfico / apfiquei".

   Decisão: **a IA nunca adivinha flexão**. Toda forma vem do MorphoBr, com a tabela verbal completa de 63 formas.
2. **A coordenação de infinitivos** ("mostrar ou ocultar", "adicionar ou remover") está declarada no módulo
   `Extend` mas **não implementada** para as línguas românicas (`MkVPI` e `ConjVPI` = `variants {}` em
   `ExtendRomanceFunctor.gf`). É uma construção geral da língua a implementar por nós.
3. **Falhas restantes, por padrão:**
   - siglas e estrangeirismos (`SVG`, `URL`, `ID`, `X`/`Y`, `padding`);
   - compostos no léxico da gramática (`quadro-chave`, `pré-visualização`);
   - contração com demonstrativo (`desta`);
   - substantivo + substantivo ("tamanho base");
   - particípio como adjetivo ("texto transbordado");
   - nome sem artigo depois de preposição ("com retângulo");
   - predicativo com "como" ("salvar os estilos como classe").
4. **Ambiguidade:** a mediana de 3 análises por rótulo é administrável; a cauda chega a 280. Escolher entre as análises
   é papel da interpretação por abdução contra o manifesto (plano, §1). A gramática sozinha não decide.

**Conclusão do X1 (viabilidade):** **sim**. Sem escrever nenhuma regra de domínio, a gramática aberta + morfologia exata
analisam ~90% da linguagem humana do builder. As falhas têm causas identificadas e são todas construções *gerais* do
português (coordenação, siglas, compostos, aposição), não vocabulário de domínio.

**Custo:**
- a gramática compilada ocupa 4,3 MB;
- a morfologia vem dos dados do MorphoBr (623 MB brutos; o índice compacto ainda está por medir);
- as ~40 s por 584 frases (~70 ms por frase) incluem compilar a gramática a cada execução.

### X1c — Ativar as construções do `Extend` sem restrição (resultado negativo)

Ativamos `CompoundN`, `PastPartAP` e `ApposNP` do módulo `Extend` sobre a gramática inteira:

| Medida | Valor |
|---|---|
| Memória do GF | **mais de 21 GB** (processo interrompido por nós para proteger a máquina) |
| Ambiguidade máxima | **~9 milhões de análises** para um único rótulo |
| Cobertura até a interrupção | 57% (a medição não chegou ao fim) |

**Causa:** `CompoundN : N -> N -> N` é recursiva. Sobre um léxico de 800 entradas, sequências de substantivos geram um
número exponencial de árvores.

**Decisões:**
1. Compostos entram **pelo léxico** (compostos observados, como `quadro-chave`), não por uma regra recursiva geral.
2. Toda análise roda com **teto de resultados** e **ordenação por pesos** aprendidos por contagem (a gramática
   probabilística do plano), nunca enumerando tudo.
3. Todo experimento com gramática roda com um **limite de memória e de tempo**, vigiado pelo harness.

**Próximo passo:**
- implementar a coordenação de infinitivos (ausente no GF românico);
- tratar siglas e estrangeirismos como nomes do léxico;
- aplicar as construções do `Extend` de forma restrita e medir de novo.

## M2 — Planejar sobre o builder-6 real

**Pergunta:** a partir do estado inicial de cada cenário do builder-6 (fixture, seleção, idioma, breakpoint, estado) e
só do **documento esperado**, o planejador chega a esse documento usando os comandos reais do editor, sem ver os passos
do cenário?

**Método:**
- **Problemas:** os 1.023 cenários do manifesto do builder com diferença de documento esperada.
- **Sucesso:** o `matchDocument` do próprio builder aceita o documento final, e o validador do builder aceita todo
  estado confirmado.
- **Verificação independente:** cada plano resolvido é refeito do zero, numa nova montagem.
- **Conjunto alcançável:** quantos cenários o editor sem interface reproduz com os **passos originais**
  (`experiments/m2_replay.py`). Esse é o teto: 798 de 1.023. Os demais dependem de arquivos, área de transferência,
  geometria medida em pixels ou importação de HTML.
- **Modelo de efeitos** (`nucleo/builder/effects.py`): aprendido por experimentação nas fixtures, com argumentos
  tirados só dos domínios do manifesto. Os objetivos nunca são lidos nessa fase. Levou 6 s e observou 68 comandos com
  efeito, com 6 generalizações paramétricas (por exemplo, `style.set` escreve exatamente a propriedade do seu
  argumento `property`).
- **Planejador** (`nucleo/builder/planner.py`):
  - diferença estruturada entre o estado e a meta;
  - relevância **deduzida pelo núcleo lógico** (regras sobre os fatos aprendidos, com prova checável);
  - argumentos abduzidos do próprio item da diferença e filtrados pelo tipo declarado no manifesto;
  - pré-condições por meios-fins (selecionar o nó; mudar a camada de breakpoint ou estado);
  - busca best-first pela distância em folhas.

**Resultado** (1.023 cenários, 183 s):

| Medida | Valor | Meta (§11) |
|---|---|---|
| Objetivos alcançáveis resolvidos | **676 / 798 = 84,7%** | ≥ 80% |
| Todos os objetivos | 800 / 1.023 = 78,2% | — |
| Planos resolvidos confirmados ao refazer do zero | **800 / 800** | 100% |
| Mesmo comando principal do cenário | 458 / 800 | não é meta: planos alternativos válidos contam |
| Nomes de nós trocados por palavras inventadas (758 renomeáveis) | 602 → 599 (−0,4 ponto) | queda ≤ 1 ponto |

O planejador resolve 124 cenários que os passos originais não reproduzem sem interface. Ele encontra outro caminho:
por exemplo, `selection.select` + `element.moveTo`, onde o cenário usava um arrastar medido em pixels.

**Evolução da heurística (registro honesto):**
- Na primeira versão, a distância era a contagem do `matchDocument`: 58,9% dos alcançáveis. Essa contagem trata um
  objeto `styles` ausente como uma divergência só. Por isso, pôr `display:flex` antes de `flex-direction`, ou inserir
  uma imagem antes de definir o `src`, não contava como progresso, e a busca podava o passo.
- Trocada pela distância em folhas (cada propriedade, atributo, classe ou texto que falta conta 1), a taxa subiu para
  84,7%. O `matchDocument` continua sendo o juiz do sucesso.

**Limites conhecidos:**
- Entre planos equivalentes no documento, o planejador não prefere o de menor efeito colateral. Ele pode escolher
  `clipboard.cut` onde `element.delete` bastaria, porque os dois têm o mesmo efeito observado no documento.
- As falhas restantes entre os alcançáveis concentram-se em comandos cujo efeito a exploração não observou
  (`style.setShadows`, `element.setTag`, `element.setLink`: argumentos com formato próprio) e em metas de vários
  itens que exigem mais passos do que o orçamento de expansões.

## M3 — O mundo do código: resolução de nomes por regras, julgada pelos compiladores

**Pergunta:** o núcleo lógico, recebendo só fatos **sintáticos** (escopos, declarações e usos, lidos da árvore
sintática, sem verificador de tipos), deduz a que declaração cada nome se refere com a exatidão do próprio compilador?

**Método:**
- **Regras** (`nucleo/code/resolve.py`, 12 linhas de Datalog) iguais para TypeScript e Python:
  - busca pelo escopo e pelos escopos envolventes;
  - parada no primeiro escopo que declara o nome num espaço compatível: negação sobre mundo fechado;
  - `#min` entre declarações mescladas;
  - "externo" quando nenhum escopo declara o nome.

  Só o extrator conhece a linguagem:
  - TypeScript (`bridge/code/ts_facts.mjs`): `var` e declarações de função, blocos, espaços de valor e de tipo;
  - Python (`nucleo/code/python_facts.py`): classe invisível para funções aninhadas, `global`/`nonlocal`, PEP 695,
    mangling de `__nome`.
- **Entre arquivos** (`nucleo/code/modules.py`): a resolução de caminho de módulo é fato do compilador, com
  proveniência. As cadeias de `import`/`export`/`export *`/reexportação são deduzidas por regras.
- **Oráculos:**
  - resolução de nomes: `checker.getSymbolAtLocation` do TypeScript e `symtable` do CPython;
  - resolução entre arquivos: `getAliasedSymbol` do TypeScript;
  - consultas sobre o projeto: o `findReferences` do serviço de linguagem do TypeScript.

**Resultado:**

| Corpus | Usos | Precisão | Cobertura | VERDADEIRO errado |
|---|---|---|---|---|
| builder-6 (TS, 320 arquivos) | 72.149 | 100% | 100% | 0 |
| builder-5 (TS, 284) | 68.099 | 100% | 100% | 0 |
| Road (TS, 182) — **validação** | 79.833 | 100% (antes do ajuste: 100% / 99,993%) | 100% | 0 |
| zerto-studio (TS 7, 14) — **validação** | 7.468 | 100% | 100% | 0 |
| stdlib do Python 3.12 (163) — **validação** | ~103 mil | 100% (antes dos ajustes: 99,992%) | 100% | 0 |
| site-packages (pytest, hypothesis, clingo, pip…; 1.037) — **validação limpa** | 229.116 | **100%** | **100%** | **0** |

| Consulta | Resultado |
|---|---|
| Importações até a declaração de origem | builder-6 4.188/4.188; builder-5 3.699/3.699; Road 2.094/2.094; zerto 153/153 |
| "Todas as referências" contra `findReferences` | builder-6: 864/864 em 185 declarações; Road: 5.869/5.869 em 1.011 declarações |
| Incremental por arquivo | 7 alterações reais (builder-5 → builder-6): **igual à reconstrução completa** |

A meta do §11 era P ≥ 99,5% / C ≥ 97% e "VERDADEIRO errado" ≤ 0,1%.

**Honestidade sobre a validação:**
- As regras foram corrigidas olhando os erros do builder-6, do Road e da stdlib. Por isso o número *antes* de cada
  ajuste está registrado.
- O conjunto site-packages só foi usado depois de todos os ajustes: é o resultado de validação limpo.

**Limites:**
- **Manutenção incremental:** o cone é calculado por predicado. A mudança de um arquivo recalcula a relação
  `alcanca` do projeto inteiro: ~5 s por atualização, contra 14 s da reconstrução. Para milissegundos é preciso
  manutenção por tupla (DRed / contagem), prevista para o porte em Rust (R1).
- **Membros de objeto** (`a.b`) dependem de tipos. Eles não são resolvidos por essas regras. O plano é trazê-los como
  fatos do compilador, com proveniência.

## M4 — Conhecimento de APIs e da web, sem chave e sem custo

### Diferenças de API entre versões reais, julgadas pelo compilador

- **Superfície de API** (`bridge/code/api_surface.mjs`): as exportações do módulo de tipos de cada pacote, lidas pelo
  compilador TypeScript, com espaço (valor, tipo, ambos) e assinatura.
- **Diferença por regras** (`nucleo/apis/surface.py`): `indisponivel(N, espaço)`, `novo(N, espaço)`,
  `assinatura_mudou(N)`.
- **Juiz:** para cada nome, um arquivo de sonda que o importa no seu espaço é **compilado de verdade** contra a outra
  versão.
- **Pares:** 35 pacotes com tipos, instalados em versões diferentes nos projetos locais. Por exemplo: vitest 4.1 → 5.0,
  keyv 4 → 5, magic-string 0.30 → 1.4, @types/node 24 → 26, tinybench 2 → 6, typescript 5.9 → 7.0.

| Rodada | Acordo com o compilador | O que mudou |
|---|---|---|
| 1 | 96,58% | — |
| 2 | 98,99% | sonda: erro de aridade genérica (TS2314/2707) não significa ausência |
| 3 | 99,53% | extrator: `export type { Classe }` exporta só o tipo; `export =` oferece `default` |
| 4 | **99,98% (4.446 / 4.447)** | sonda: namespace usado como tipo (TS2709) não significa ausência |

A divergência restante é o `default` sintético do `typescript` 7 (pacote nativo em Go).

### Web sem chave: robots.txt, registros e "aprovar antes de aprender"

- **Buscador** (`nucleo/web/fetcher.py`):
  - lê o `robots.txt` antes de qualquer requisição (RFC 9309, com os curingas `*` e `$`);
  - identifica-se, espera ≥ 1 s por host e usa GET condicional com cache;
  - tem limite de tamanho;
  - quando recebe uma página de desafio anti-robô, registra "bloqueado" e **não a contorna**.
- **Registros** (`nucleo/web/registries.py`): primeiro o que está instalado; depois o npm (JSON de metadados) e o PyPI
  (feed RSS de versões).
- **Alegações** (`nucleo/web/claims.py`):
  - toda alegação entra no contexto `web_nao_verificada`;
  - regras decidem a verificação: fonte estruturada reproduzida, ou duas fontes de sites independentes;
  - só a **aprovação do usuário** promove a alegação ao contexto `conhecimento`;
  - só um pacote cuja existência é conhecimento pode ser sugerido.

**Resultado ao vivo** (`experiments/m4_packages.py`, 33 requisições):
- 10 pacotes reais confirmados e sugeríveis;
- 13 nomes inventados ou com grafia errada de pacotes populares recusados pelo registro, **0 sugeridos**;
- **0 violações** de robots.txt.

**Descobertas sobre as fontes** (detalhes em `docs/achados.md`):
- **PyPI:** o `robots.txt` proíbe a API JSON (`/pypi/*/json`) e o `/simple/`, e as páginas de projeto respondem a robôs
  com um desafio em JavaScript. Resta o feed RSS, que é permitido.
- **deps.dev:** a API (`api.deps.dev`) proíbe tudo no `robots.txt`.
- **Python:** o `urllib.robotparser` da biblioteca padrão ignora os curingas da RFC 9309 e diria "permitido" para a
  API JSON do PyPI. Por isso o buscador usa o seu próprio avaliador, testado contra a tabela de exemplos publicada pelo
  Google.

**Pendências do M4:**
- **SearXNG local:** exige instalar Docker ou o serviço; é decisão do usuário.
- **Fatos de BCD/webref:** os dados já estão no `node_modules` do builder. Entram com o M6, onde servem para validar o
  CSS gerado.

## X2 — Analisador sintático linear, sem rede neural, para o português

**Método:**
- **Etiquetador:** perceptron médio, com atributos de palavra, afixos, forma e vizinhos, mais a **classe de
  ambiguidade do MorphoBr** (as categorias possíveis de cada palavra).
- **Analisador:** arc-hybrid com oráculo dinâmico (Goldberg & Nivre) e um rotulador de relações separado. Os modelos
  são dicionários de pesos em JSON.
- **Treino:** Bosque + PetroGold + Porttinari, com 20.081 frases e 10 épocas (~13 min em Python puro).
- **Juiz:** as divisões de teste dos próprios treebanks, anotadas por humanos, com tokenização-ouro e sem contar a
  pontuação.

| Treebank | UPOS | UAS | LAS | LAS com etiquetas-ouro |
|---|---|---|---|---|
| Bosque | 95,48% | 84,45% | 77,28% | 80,16% |
| PetroGold | 98,05% | 88,39% | 82,71% | 84,24% |
| Porttinari (PT-BR) | 96,69% | 86,49% | **80,07%** | 82,92% |
| imperativas (12 frases de teste) | 93,10% | 81,28% | 70,94% | — |

- **Efeito dos atributos do MorphoBr:** +0,3 a +0,5 no LAS e +3,5 no UAS das imperativas.
- **Referência neural:** UDPipe 2 e Stanza ficam em LAS ~80–95.
- **Decisão prevista no plano (LAS < 80 em parte dos casos):** a semântica não confia cegamente na árvore.
  - O léxico reordena o predicado quando a etiqueta erra ("ajuste": substantivo para o etiquetador, subjuntivo de
    "ajustar" para o MorphoBr).
  - Os argumentos são lidos por pedaços entre preposições, então uma anexação errada não apaga um argumento.

## M5 — Português → restrições → planejador → documento do builder

**Método:**
- **Compreensão** (`nucleo/lang/understand.py`):
  - tokenização com literais protegidos (funções CSS, cores, medidas, aspas);
  - análise sintática do X2;
  - predicado e argumentos;
  - ancoragem no **léxico construído do catálogo pt-BR e do manifesto do builder** (`lexicon.py`: tipos, 751 nomes de
    propriedade CSS com os do W3C, atributos, estados, breakpoints);
  - **abdução ponderada** sobre os quadros verbais (`frames.json`: estado-resultado, nunca comando).
- **Decisão:** executar, perguntar ou "não entendi".
  - Um verbo desconhecido **nunca** executa.
  - Um referente com vários candidatos **nunca** é escolhido em silêncio.
  - Uma palavra ignorada que nomeia algo do builder custa caro.
- **Execução:** as restrições são o objetivo do planejador do M2, e o plano sai da busca ("inserir e depois editar o
  texto" surge sozinho).
- **Juiz:** o documento esperado de cada cenário do builder, pelo `matchDocument` do builder.
- **Pedidos de teste:** gerados por um realizador separado (`tests/gen/requests.py`), com variação de verbo,
  modo ("insira", "insere", "inserir", "você pode…?", "por favor", "quero que você…"), ordem valor-primeiro,
  contrações, camadas e nomes inventados. Metas não descritíveis numa frase (listas de sombra, campos fora do padrão)
  são puladas, nunca descritas pela metade.

**Resultado** (meta do §11: top-1 ≥ 80%, erro silencioso ≤ 2%):

| Variante | Pedidos | top-1 | Erro silencioso | Perguntou ou não entendeu |
|---|---|---|---|---|
| frases originais | 664 | **88,1%** | **0,0%** | 9,9% |
| … cenários 1–300 (ajuste) | 259 | 94,2% | 0,0% | |
| … cenários 301+ | 405 | 84,2% | 0,0% | |
| nomes de nós inventados | 571 | 88,6% | 0,0% | 9,5% |
| frases novas (outra semente) | 662 | 87,6% | 0,0% | 10,6% |

**Honestidade sobre a validação:**
- As regras foram ajustadas olhando os cenários 1–300.
- Numa segunda rodada, olhei os **erros silenciosos** dos cenários 301+ para achar causas gerais:
  - o tokenizador que partia `blur(4px)`;
  - a porta de CSS sem validação;
  - estados de estilo ignorados;
  - campos do nó fora da comparação.

  Antes dessa rodada, os cenários 301+ davam top-1 57,0% e **12,0% de erro silencioso**.
- As variantes com nomes inventados e com frases novas foram geradas depois de todos os ajustes.

**Limites:**
- **Frases de um só pedido.** Uma frase com "e também" não é executada pela metade.
- **Vocabulário do catálogo.** "Cor de fundo" não é reconhecida, porque o builder chama `background-color` de "Fundo".
  Aprender sinônimos por definição é o M8.
- **Gerador escrito por mim.** A diversidade de paráfrase humana real só virá com o uso.

## M6 (parcial) — Reconstruir corpos de funções apagadas a partir de exemplos

**Método:**
- **Tarefas:** funções pequenas e puras (`return <expressão>`) da biblioteca padrão e dos pacotes instalados.
  - O oráculo é a própria função original, executada em entradas geradas.
  - A tarefa recebe 6 exemplos de treino e é julgada em 30 entradas que nunca viu.
- **Sintetizador** (`nucleo/synth/enumerate.py`):
  - enumeração de baixo para cima por níveis de custo, com equivalência observacional;
  - constantes tiradas dos exemplos;
  - opcionalmente, uma gramática probabilística contada no corpo de código, sem o arquivo da tarefa.
- **SyGuS e MBPP** (as referências do plano) exigem download, que depende de autorização do usuário.

**Resultados, em ordem cronológica:**

| Rodada | Uniforme | Com prior contado | O que mudou |
|---|---|---|---|
| 1 | 26,0% | 43,2% | enumerador ineficiente (combinava tudo com tudo) |
| 2 | 68,5% | 73,3% | enumeração por níveis de custo |
| 3 (amostra de 63 tarefas) | **57,1%** | **57,1%** | testes corrigidos: entradas que exercitam o corpo original; tarefas que a identidade já passava foram descartadas |

**Leitura honesta:**
- **A rodada 2 estava inflada.** Por exemplo, `str.replace('\\', '\\\\')` era "reconstruído" como `str`, porque as
  entradas de teste nunca continham barra invertida.
- **O prior deixou de fazer diferença.** Com os testes corrigidos, a vantagem da gramática contada desaparece nesta
  amostra: as tarefas que restam são pequenas demais para ela importar.
- **Não é geração de código útil ainda.** A síntese resolve expressões curtas (operadores, métodos de string, tuplas).
  Gerar e corrigir código com vários arquivos, como no plano (modelo → geradores, clichês, reparo), não foi feito.

**Custo:** a rodada completa travou o computador do usuário. Os experimentos agora rodam em prioridade baixa, em
amostras.

## M6 — Modelo → projeto de vários arquivos em TypeScript e Python, verificado

**Método:**
- **Entrada:** um modelo declarativo do projeto (`nucleo/gen/model.py`): entidades; campos tipados (texto, inteiro,
  decimal, booleano, enum); restrições (obrigatório, mín./máx., formato e-mail, valores); relações.
- **Saída:** geradores determinísticos produzem, nas duas linguagens:
  - TypeScript: tipos, validadores, um repositório em memória com integridade referencial, e testes;
  - Python: dataclasses, validadores, o mesmo repositório, e testes.
- **Verificação**, sem a palavra de ninguém valer como prova:
  1. o compilador TypeScript em modo estrito (`noUncheckedIndexedAccess`) não acusa nada;
  2. os testes gerados passam em Node e em pytest;
  3. **teste diferencial:** valores aleatórios são julgados pelo validador TS, pelo validador Python e pelo significado
     de referência do modelo, e os três precisam dar os mesmos códigos de erro. Os valores incluem válidos e
     quebrados, unicode, emojis nos limites de tamanho, floats, booleanos, nulos e tipos errados.

**Resultado** (`experiments/m6_multifile.py`, 30 modelos aleatórios com nomes inventados, 1 a 4 entidades):

| Medida | Valor |
|---|---|
| Projetos verificados | **30 / 30** (meta do §11: 100%) |
| Código gerado | 330 arquivos, 15.735 linhas |
| Valores no teste diferencial | 9.000, **0 divergências** |
| Tempo | 70 s, em prioridade baixa |

**A verificação pega defeitos?** Defeitos injetados de propósito nos geradores:

| Defeito injetado | Modelos em que foi detectado |
|---|---|
| TS conta o tamanho em unidades UTF-16 (`s.length`) | 1/12 → **11/12**, depois de reforçar o fuzz com emojis nos limites |
| Python usa `<=` em vez de `<` no mínimo | **10/12** |

**Defeitos reais pegos pela verificação durante o desenvolvimento:**
- `VALIDATORS` tipado como `Record<string, …>`: com acesso estrito, cada chamada podia ser `undefined` (pego pelo `tsc`).
- `false` do JSON escrito dentro de código Python (pego pelo pytest).

**Limites:**
- **Domínio fixo:** o gerador cobre um tipo de projeto (dados, validação, repositório). Não há rotas HTTP nem
  interface.
- **Modelo em JSON:** o modelo é escrito como dado, ainda não a partir de uma frase em português.
- **Não é síntese:** é geração a partir de modelo (MDE), como previsto no plano. O código é correto por construção e
  por verificação, não inventado.

## M7 — Reparo de defeitos em funções reais, julgado em entradas nunca vistas

**Método** (`nucleo/repair/templates.py`, `experiments/m7_repair.py`):
- **Defeitos:** injetados nas funções reais do corpo de código (as tarefas do M6, com testes que distinguem). Um
  defeito só vale se falhar em pelo menos um dos 6 testes visíveis.
- **Reparo:** templates de correção no estilo TBar. Trocar um operador pelo seu irmão; constante ±1; inverter
  operandos; pôr ou tirar negação; método irmão (strip/lstrip/rstrip, startswith/endswith…); outra variável. A busca
  vai da menor edição para a maior (até 2).
- **Juiz:** a função original, em 30 entradas que o reparo nunca viu. "Sobreajustado" é o reparo que passa nos testes
  visíveis e falha nos escondidos, o problema do GenProg: 2 de 105 corretos.
- **QuixBugs e BugsInPy** (as referências do plano) exigem download, que depende de autorização.

**Resultado:**

| Tipo de defeito | Defeitos | Corretos | Sobreajustados | Não reparados |
|---|---|---|---|---|
| do tipo que os templates desfazem | 94 | **91,5%** | 1,1% | 7,4% |
| **fora dos templates** (constante ±2..5, chamada removida, método sem parentesco, operando trocado por constante) | 52 | **32,7%** | 1,9% | 65,4% |

**Leitura honesta:**
- **A primeira linha é otimista por construção:** os defeitos vêm das mesmas edições que o reparo sabe desfazer.
- **A segunda linha é a mais realista.**
- **O que se sustenta nos dois casos é o baixo sobreajuste.** Com testes que distinguem e a preferência pela menor
  edição, o sistema raramente propõe um "conserto" que só passa nos testes visíveis. Quando não sabe, não propõe.

## R1 — Portar para Rust? (medido e decidido)

**Medições atuais** (Python, prioridade baixa, a máquina do usuário):

| Operação | Tempo |
|---|---|
| Pedido em português ao builder (entender + planejar + executar) | ~0,1 s |
| Montar o conhecimento do código do builder-6 (320 arquivos) | ~19 s, uma vez por sessão |
| Pergunta sobre o código (definição, usos, impacto) | 0,00–0,03 s |
| Atualização incremental de um arquivo alterado | ~5 s |
| Gerar e verificar um projeto de vários arquivos | ~2 s |

**Decisão:** não portar agora.
- O uso interativo já responde em frações de segundo.
- Os custos que pesam são a montagem inicial do índice (19 s) e o incremental (5 s). Os dois vêm de o motor recalcular
  por predicado, não da linguagem (achado M3-7). A primeira melhoria é algorítmica (manutenção por tupla, DRed); o porte
  em Rust vem depois, com a mesma bateria diferencial do M1.
- Não há toolchain de Rust na máquina. Instalá-lo exige download, que depende de autorização do usuário.
