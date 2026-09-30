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
