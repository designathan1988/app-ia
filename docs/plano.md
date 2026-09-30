# Plano aprovado: motor cognitivo de programação, sem LLM

## Contexto

- **A tentativa anterior falhou.** A auditoria do COGNITA (`C:\Codex-Shared\IA\audit\`) mostrou um reprodutor de molde, com matemática decorativa e sem conhecimento explícito.
- **O que o usuário quer:** uma IA própria que **programa**:
  - gera e modifica páginas e componentes no builder-6 (`C:\Codex-Shared\deepseek\builder-6`);
  - escreve código geral em HTML/CSS, JS/TS e Python, **longo e com vários arquivos**;
  - entende, modifica e corrige código;
  - aprende com o uso;
  - consulta a web em tempo real sem API e sem custo;
  - mantém um banco de fontes, métodos, preferências e memória.
- **Restrições:**
  - **proibido qualquer LLM**, de terceiros ou próprio;
  - nada de regex, palavra-chave ou `if/else` decidindo intenção;
  - nada de respostas prontas;
  - local; RTX 3060; Python agora e Rust depois; repositório novo;
  - o usuário não escreve nem anota nada.
- **Base de evidência:** a Parte II deste documento, com 90+ técnicas pesquisadas e fontes.

### Tese central, sustentada pela pesquisa

1. **Compreender é explicar.** A frase vira uma forma lógica por gramática composicional. A interpretação é a **explicação de menor custo** dessa forma contra o que o sistema sabe do documento, do código e do projeto (abdução ponderada, Hobbs 1993). Se nenhuma explicação é boa, o sistema **pergunta** em vez de chutar (PRECISE, predição unânime, GoDiS).
2. **Palavras são ancoradas em ações e efeitos verificáveis**, não em outras palavras (Harnad, SHRDLU):
   - "botão" é um tipo do manifesto;
   - "centralizar" é uma restrição sobre a geometria renderizada;
   - "a função que valida" é um símbolo da base de código.
3. **A precisão vem de operar sobre modelos tipados.** Linguagem natural → DSL tipada chega a 78–94% top-1 sem LLM (SmartSynth, NLyze, SQLizer, ATHENA). Modelo → geradores produz milhares de linhas consistentes entre arquivos (MDE, JHipster). **O builder-6 já é uma DSL tipada:** manifesto, comandos, validador.
4. **Código longo = compor planos conhecidos.** A decomposição hierárquica (HTN) e os clichês (Programmer's Apprentice: comandos 10× mais curtos que o código) produzem a estrutura. A **síntese** preenche só os buracos locais, que é onde ela funciona: 5 a 100 nós de AST. A **verificação** fecha o ciclo.
5. **"Exato e funcional" tem definição operacional.**
   - Estrutura, tipos e segurança ficam **garantidos por construção**.
   - O comportamento fica **garantido contra a especificação verificada**: contratos, propriedades, testes gerados, exemplos, validadores.
   - Sem especificação suficiente, a IA a obtém: pergunta, pede um exemplo, deriva do contexto.
   - **Nenhuma saída sai sem o relatório do que foi verificado.**
6. **Aprender é acrescentar conhecimento explícito, com viés indutivo declarado** (Mitchell 1980). O conhecimento aprendido pode ser vocabulário, construções, procedimentos, clichês, padrões de correção, convenções ou crenças sobre fontes. Os vieses são:
   - tipos e manifesto (domínio);
   - MDL (simplicidade);
   - biblioteca aprendida (analogia);
   - preferências do usuário (uso pretendido).

   Não há retreino de pesos, então não há esquecimento.

## 1. Decomposição das capacidades → mecanismo escolhido

| Capacidade | Mecanismo (nós da Parte II) |
|---|---|
| Normalizar texto informal | Léxico de variantes + fonética (estilo UGCNormal). Identificadores protegidos. Correção por canal ruidoso com contagens. |
| Morfologia | MorphoBr / DELAF-PB compilados em transdutor finito (exato) |
| Sintaxe | Analisador por transições com **modelo linear** (perceptron médio, sem rede neural), treinado em Porttinari + Bosque + PetroGold + um treebank de pedidos que cresce com o uso. Saída n-best. |
| Semântica composicional | **Núcleo GF** (RGL português, bidirecional) para frases canônicas + regras UD→FL (UDepLambda / ud2gf) para frases livres. Negação, quantificadores e modais vêm do tipo semântico dos lexemas funcionais. |
| Interpretação e referência | **Abdução ponderada** sobre os mundos ancorados. Entidades de discurso (DRT). Poda por tipo (SQLizer). Teste de tratabilidade (PRECISE). |
| Diálogo | Estado de informação com perguntas em discussão (GoDiS). Esclarecimento só quando a ambiguidade muda o resultado, escolhido por ganho de informação. Paráfrase de volta pela linearização GF. |
| Representar e lembrar | Base Datalog com proveniência, status epistêmico (conhecido, inferido, presumido, hipotético, contraditório, indeterminado, desconhecido), contextos isolados (projeto, sessão, hipótese, web não verificada; microteorias do Cyc) e manutenção incremental (DRed / IncA) |
| Entender código | Fatos de sintaxe (tree-sitter) + **fatos do compilador** (TypeScript 6 checker, pyright) + regras de análise (estilo CodeQL / Doop) + **reconhecimento de clichês** (GRASPR) + fatos de testes e cobertura |
| Raciocinar | Dedução (Datalog), abdução (interpretação, diagnóstico de bugs), analogia (SME sobre casos e clichês), restrições (ASP/clingo para espaços discretos, MILP/CP-SAT para layout, Cassowary para responsividade), modelos causais ação→efeito (estilo AERA) |
| Planejar | **HTN** cujos métodos são clichês e procedimentos aprendidos, e cujas ações primitivas são comandos do builder ou edições de AST. Busca A* sobre os comandos reais do builder rodando sem interface. |
| Gerar páginas | Plano de comandos + layout por otimização (estilo GRIDS) com **métricas estéticas** (Ngo) + tokens de design do projeto. Verificação por validador, exportação e geometria renderizada (estilo Cassius). |
| Gerar código geral | (a) **Modelo do projeto** → geradores determinísticos de vários arquivos. (b) Composição de clichês (KBEmacs). (c) Buracos por síntese: enumeração tipada guiada por **gramática probabilística aprendida por contagem** (Euphony/PHOG), domínios abstratos (Absynthe), exemplos (λ²/FlashMeta), composição de API (SyPet/Hectare), expressões (cvc5), equivalência por e-graph (egg). (d) Lógica crítica opcional em Dafny → JS/Python. |
| Verificar | tsc6/pyright, lint, `validateDocument` do builder, html-validate, gramáticas CSS do webref (css-tree), testes existentes + gerados (Pynguin, CrossHair, fast-check/Hypothesis a partir da especificação), execução em sandbox (Deno sem permissões / gVisor), teste diferencial |
| Corrigir | Localização de falha por espectro de testes + templates (TBar) + **padrões mineirados do histórico** (Getafix) + reparo semântico com SMT quando há especificação (Angelix). Nunca aceitar um patch só porque "os testes passam" (anti-sobreajuste). |
| Aprender linguagem | Definições pelo usuário (**Voxelurn**: 85,9% dos comandos passaram a usar sintaxe ensinada pelos usuários), pares (pedido, ação confirmada) (Kwiatkowski, Chang, aprendizado entre situações), crescimento do treebank |
| Aprender procedimentos | Demonstração na interface (SUGILITE, HTN-Maker), instrução (Rosie), compilação da experiência (chunking / EBL) |
| Aprender código | **Stitch** (biblioteca de clichês por compressão), Getafix (correções), contagens PHOG, **ILP** (Popper/MaxSynth) para as convenções do projeto |
| Crenças e preferências | Valor de verdade por evidência (frequência, confiança, estilo NARS), revisável, com fonte |
| Web atualizada | SearXNG local + fontes estruturadas (BCD, webref, typeshed, `@types`, npm/PyPI, OSV, DevDocs) → **alegações com fonte** → verificação → promoção para conhecimento |
| Explicar | Árvore de prova → texto pela gramática GF (estilo RACE / PROVERB), citando arquivo:linha e fontes |

## 2. Arquitetura

```
 PT-BR ─► NORMALIZA ─► MORFO(FST) ─► SINTAXE(linear, n-best) ─► SEMÂNTICA(GF núcleo + UD→FL) ─► FL
                                                                                          │
                       ┌──────────────── INTERPRETAÇÃO = ABDUÇÃO PONDERADA ───────────────┘
                       ▼                (custo mínimo contra os mundos; se alto → perguntar)
        ┌────────────── MUNDOS ANCORADOS (fatos + regras + proveniência + status) ──────────────┐
        │ Builder: manifesto→ontologia+ações; DocumentJson; handlers sem interface = transição  │
        │ Código:  AST + compilador + clichês + testes/cobertura                                │
        │ APIs:    webref/BCD/typeshed/@types versionados;  Web: alegações não verificadas      │
        │ Memória: episódica · preferências · léxico · procedimentos · clichês · fontes         │
        └───────────────────────────────────┬──────────────────────────────────────────────────┘
                     RACIOCÍNIO: dedução · abdução · analogia · restrições · planejamento HTN
                                            │
          GERAÇÃO: comandos do builder · modelo→geradores · clichês · síntese de buracos · texto GF
                                            │
          VERIFICAÇÃO: tipos · validadores · testes (existentes + gerados) · sandbox · prova
                                            │  falhou → reparo / nova hipótese / pergunta
                                   RESPOSTA + PATCH + EXPLICAÇÃO + RELATÓRIO DO QUE FOI VERIFICADO
                                            │
          APRENDIZADO: léxico/construções · métodos HTN · clichês (Stitch) · padrões de correção ·
                       convenções (ILP) · contagens PHOG · crenças/preferências   → base (sem pesos)
```

**Alternativas descartadas:**

| Alternativa | Motivo |
|---|---|
| LLM (de terceiros ou próprio) | Proibido. Sem garantia. Pesado. |
| Rede neural de ponta a ponta | Refutada pela auditoria |
| Ranqueador neural | Substituído por modelos lineares e contagens (PHOG, log-linear), que são pequenos e explicáveis |
| Busca de código por embeddings | Não verifica nem compõe |
| Gerar tudo por síntese | Não escala além de ~100 nós |
| Reparo guiado só por testes | Sobreajusta: 2/105 corretos no GenProg |
| Gramática de precisão feita à mão (estilo ERG) | Décadas de trabalho → GF núcleo + analisador estatístico linear + aprendizado com o uso |
| Clifford, geometria hiperbólica, álgebras de operadores | Nenhuma tarefa de código ou de página que as exija |

## 3. Dados e representação

**Estrutura:**
- **Um só formato de fato:**

  ```
  (pred, args, polaridade, contexto, fonte, versão, confiança, prova)
  ```

- **Esquema como dado.** Contextos isolados: `projeto`, `sessão`, `hipótese`, `web_nao_verificada`, `usuario`.
- **FL** (forma lógica): eventos neo-davidsonianos + ato de fala (perguntar, criar, modificar, remover, explicar, corrigir, gerar) + entidades de discurso + negação, quantificadores e modalidade como operadores.
- **Especificação de geração:** tipos + contratos + exemplos + propriedades + testes + restrições de design + preferências.

**Banco (SQLite + FTS5):**
- `source`, `document`, `claim`, `symbol`, `compat`, `package_version`, `api_diff`
- `fact`, `rule`, `proof`
- `lexeme`, `construction`, `method` (HTN), `cliche`, `fix_pattern`, `convention`
- `preference`, `episode`, `session`, `sync_state`

**Orçamento:**

| Item | Tamanho |
|---|---|
| Sistema (código, gramáticas, léxicos, pesos lineares do analisador) | ≤ 200 MB |
| Espelho de dados técnicos (dado, não modelo) | 1–2 GB, opcional e incremental |

## 4. Raciocínio e prova

Mantêm-se as decisões validadas na revisão anterior:

**Motor lógico:**
- Datalog estratificado.
- Negação forte como predicado separado.
- Negação por falha só sobre predicados fechados; sobre predicados abertos, status **PRESUMIDO**.
- Agregados com limites em mundo aberto.
- Regras derrotáveis só em conjuntos derrotavelmente estratificados, com **INDETERMINADO** quando não há vencedor.
- Semântica de *snapshot* por versão.

**Provas:**
- Tipos de passo fixados desde o início: positivo; negativo por *lookup*; negativo com certificado de conjunto fechado; built-in com certificado; agregado; derrota; versão.
- Checador independente de provas.

**Abdução:**
- Busca de melhor explicação com custo por suposição, saliência e plausibilidade.
- O custo é aprendido por contagem de interpretações confirmadas ou desfeitas pelo usuário.
- A abdução usa o mesmo motor, com hipóteses marcadas **HIPOTÉTICO** até serem confirmadas.

## 5. Memória e aprendizado

Cada tipo de aprendizado registra a origem, a evidência e a data, e pode ser revertido. Um conceito aprendido nunca apaga outro: fica no seu contexto e pode ter prioridade.

| Tipo | Gatilho | Mecanismo | Verificação antes de promover |
|---|---|---|---|
| Palavra e construção nova | Definição ("o blorfo é um card com dois botões"), ou o par (pedido, ação confirmada) | Voxelurn, aquisição estilo CCG, aprendizado entre situações | Uso bem-sucedido e não desfeito em ≥ N ocasiões |
| Procedimento | Demonstração na interface ou instrução | SUGILITE, HTN-Maker, Rosie, chunking | Replay em documentos diferentes |
| Clichê de código | Corpus do usuário e de projetos abertos | Stitch (MDL) | Ganho de compressão + uso em síntese validada |
| Padrão de correção | Histórico git | Getafix (anti-unificação) | Reprodução de correções depois da data T |
| Convenção do projeto | Código existente | Popper / MaxSynth (MDL, tolerante a ruído) | Precisão em código retido |
| Preferência | Aceitar ou desfazer | Contagem de evidência (frequência, confiança) | — |
| Conhecimento da web | Busca ou atualização | Alegação com fonte → verificação: diff de API, duas fontes, execução em sandbox | Só então sai de `web_nao_verificada` |

## 6. Contradição, incerteza, desconhecimento

- **Status fixos:**
  - VERDADEIRO ou FALSO, qualificados como afirmado, inferido, presumido ou hipotético;
  - CONTRADITÓRIO, com as duas provas e o conjunto mínimo de conflito;
  - INDETERMINADO;
  - DESCONHECIDO, com `why_not`.
- Na **compreensão**, um custo abdutivo alto vira pergunta, e uma ambiguidade que muda o resultado vira pergunta com as alternativas concretas.
- Na **geração**, quando vários candidatos passam na especificação e divergem, a IA mostra **a entrada que os distingue** e pergunta (CEGIS interativo).
- Fontes da web que discordam ficam INDETERMINADO até que a fonte estruturada, o diff de API ou a execução decidam.

## 7. Generalização (como é provada)

1. **Invariância.** Os benchmarks rodam também com identificadores renomeados e **palavras inventadas** ("põe um blorfo…" depois de defini-lo). A queda tem que ser ≤ 1 ponto percentual.
2. **Separação.** Por projeto (repositórios sorteados e congelados) e por tempo (commits depois de T).
3. **Composição.** Pedidos e especificações que combinam construções nunca vistas juntas.
4. **Transferência.** Um clichê aprendido num projeto é usado noutro. Um procedimento demonstrado num documento é reaplicado noutro.
5. **Lint anti-literal.** Nenhum literal de domínio no código do motor. O vocabulário vive só nos dados.

## 8. Linguagem natural: sequência

- **L1:** normalização + morfologia (FST).
- **L2:** analisador linear treinado em UD-PT. A meta de referência é o LAS dos analisadores neurais (84–95). O experimento X2 mede quanto se perde sem rede.
- **L3:** núcleo GF da DSL de pedidos, com o léxico inicial vindo do **catálogo pt-BR do próprio builder-6** (`src/i18n`: nomes de comandos, propriedades e elementos já em português) e dos nomes do código.
- **L4:** regras UD→FL para frases livres. Abdução contra os mundos. Tratabilidade e esclarecimento.
- **L5:** discurso e diálogo (entidades, "isso", "o de antes"; perguntas em discussão).
- **L6:** geração de respostas e explicações pela linearização GF.
- **L7:** aprendizado de vocabulário e construções (Voxelurn e pares confirmados).

## 9. Matemática que agrega valor, e só essa

| Área | Usar em |
|---|---|
| Lógica e ponto fixo | Datalog, ASP |
| Abdução ponderada | Compreensão, diagnóstico |
| Teoria de tipos | Síntese, tipagem da FL |
| E-graphs / anti-unificação | Equivalência, clichês, padrões de correção |
| MDL / teoria da informação | Critério de aprendizado |
| Estatística simbólica (PCFG/PHOG, log-linear, contagens de evidência) | Ordenar busca e interpretações |
| Otimização (MILP, CP-SAT, simplex incremental / Cassowary) | Layout |
| SMT (cvc5/Z3) | Buracos de síntese, reparo, verificação |
| Execução simbólica | CrossHair |
| Grafos | Chamadas, dependências, alcance, impacto |

**Não usar** Clifford, geometria hiperbólica nem os operadores nilpotentes e de projeção do COGNITA.

## 10. Testes adversariais (o usuário não escreve nada)

**Fontes de verdade externas ou mecânicas, que eu não controlo:**
- Compiladores e validadores (tsc6, pyright, `validateDocument` do builder, html-validate, css-tree).
- Testes do builder-6: ~680 unitários e 1.333 cenários, cujas asserções finais viram objetivos.
- Benchmarks humanos:

  | Área | Benchmarks |
  |---|---|
  | Síntese | SyGuS; MBPP e HumanEval com os testes como especificação |
  | Reparo | QuixBugs, BugsInPy |
  | Linguagem | split de teste da UD |
  | Lógica | OpenRuleBench, lógica derrotável |

- Reconstrução de funções apagadas em repositórios sorteados (a verdade são os testes originais).

**Linguagem natural:**
- Não existe benchmark PT-BR de pedidos de código; ele é criado assim:
  - o **gerador canônico da gramática** (método Overnight) produz objetivos aleatórios com a frase canônica;
  - variantes com palavras inventadas e identificadores renomeados;
  - pares mínimos gerados pela gramática (negação, quantificador) com o efeito verificado pela execução;
  - **métricas de uso real**, a mais honesta: taxa de pedidos executados sem esclarecimento e **não desfeitos**, e taxa de execuções erradas detectadas pela verificação.
- Risco declarado: a paráfrase humana diversa só vem com o uso real. Por isso L7 (aprender com o uso) é estrutural, não um extra.

**Anti-autoengano:**
- Conjuntos congelados por hash antes do código que avaliam.
- Oráculos independentes: avaliador ingênuo, clingo, Soufflé.
- Testes de mutação no motor e no checador.
- Nenhuma capacidade no README sem o relatório do portão.

## 11. Métricas diretas (metas iniciais, congeladas antes de medir)

| Capacidade | Métrica | Meta |
|---|---|---|
| Núcleo lógico | Divergência contra os oráculos; provas aceitas | 0; 100% |
| Entender código | Definições e referências contra tsc6/pyright; **VERDADEIRO errado** | P ≥ 99,5% / C ≥ 97%; ≤ 0,1% |
| Clichês | Reconhecimento num conjunto de padrões rotulados pelo próprio uso em síntese | Relatado; portão em X5 |
| Builder | Objetivos derivados dos cenários do manifesto: resolvidos; planos válidos | ≥ 80%; 100% |
| Páginas | Métricas estéticas (Ngo) ≥ as do fixture de referência; responsividade verificada em 4 breakpoints | Relatado; 100% |
| PT-BR → ação (builder e código) | Top-1 correto na DSL; **execução errada silenciosa** | ≥ 80% (referência da literatura: 78–94%); ≤ 2% |
| Esclarecimento | Precisão de "perguntar só quando muda o resultado" | ≥ 85% |
| Síntese | SyGuS PBE; MBPP com testes como especificação | ≥ 60%; linha de base X4 + 15 pontos |
| Vários arquivos | Projeto gerado a partir de modelo: typecheck + testes gerados + build | 100% passam; tamanho relatado |
| Reparo | QuixBugs corretos (não sobreajustados) | ≥ 15/40 |
| Aprendizado | Palavra inventada ensinada e usada certo em frases novas; procedimento demonstrado e reaplicado em outro documento | ≥ 90%; ≥ 90% |
| Web | Afirmações promovidas que depois se mostram falsas; pacotes inexistentes sugeridos | ≤ 1%; 0 |
| Local | Disco do sistema; RAM por 100 mil linhas; latência de um pedido simples | ≤ 200 MB; ≤ 500 MB; ≤ 1 s |

## 12. Sequência de implementação (dependências e ordem de valor)

| Etapa | Entrega | Depende |
|---|---|---|
| **F0: Fundação** | Repositório novo e CI. Semântica formal com ~40 exemplos + codificação de referência em clingo. **Ponte sem interface para o builder-6** (os handlers puros executam fora da UI; o `import.meta.glob` exige vite-node). Download e hash dos benchmarks. Este registro de pesquisa movido para `docs/pesquisa.md`. | — |
| **M1: Núcleo de conhecimento** | Fatos, contextos, proveniência, status, Datalog com provas, checador, incremental, banco SQLite. | F0 |
| **M2: Mundo do builder** | Manifesto → ontologia e esquemas de ação; `DocumentJson` → fatos; planejador HTN + A* sobre comandos reais; verificação. **Primeiro valor visível: pedidos estruturados (FL) viram edições válidas.** | M1 |
| **M3: Mundo do código** | tree-sitter + fatos do tsc6/pyright + regras de análise + incremental por arquivo + clichês básicos (GRASPR). | M1 |
| **M4: Conhecimento de APIs e web** | Ingestão de BCD, webref, typeshed e `@types` para fatos versionados. SearXNG local. Alegações → verificação → promoção. | M1 (em paralelo a M2/M3) |
| **M5: Português** | L1–L6: a FL alimenta M2 (páginas) e M3 (perguntas sobre código). | M2, M3, experimentos X1/X2 |
| **M6: Geração de código geral** | Modelo do projeto → geradores; clichês; síntese de buracos (PHOG + tipos + exemplos + SMT); verificação completa; sandbox. | M3, M4 |
| **M7: Reparo** | Localização + templates + padrões mineirados + SMT; controle de sobreajuste. | M3, M6 |
| **M8: Aprendizado contínuo** | Voxelurn, demonstração, Stitch, Getafix, ILP, preferências. Cada um entra integrado à etapa onde é usado e aqui é consolidado. | M2–M7 |
| **R1: Rust** | Porte do núcleo lógico e do incremental, com a mesma bateria diferencial. | M1 estável + medição |

## 13. Portões de aprovação

Cada etapa só é aprovada com o relatório automático do CI verde contra as metas de §11 correspondentes. Em resumo:

- **F0:** clingo reproduz os 40 exemplos; ponte executa handlers sem interface com resultado idêntico ao `vitest` do builder.
- **M1:** divergência 0; provas 100%; incremental = recomputação.
- **M2:** ≥ 80% dos objetivos dos cenários; 100% dos planos válidos.
- **M3:** P/C contra o compilador; VERDADEIRO errado ≤ 0,1%.
- **M4:** 0 pacotes inexistentes; diffs de API corretos contra o API Extractor e o griffe.
- **M5:** top-1 ≥ 80% e erro silencioso ≤ 2% nos conjuntos gerados, com palavras inventadas.
- **M6:** SyGuS ≥ 60%; projeto de vários arquivos 100% verificado.
- **M7:** QuixBugs ≥ 15/40 corretos.
- **M8:** ≥ 90% nos testes de ensinar e reaplicar.

## 14. Riscos e experimentos antecipados

| # | Risco | Experimento | Decisão |
|---|---|---|---|
| X1 | Cobertura do GF português (PT-BR?) para pedidos | Em F0: gramática de aplicação mínima sobre a RGL para 50 formas de pedido do builder | Se falhar: gramática própria de construções (estilo FCG) só para o núcleo |
| X2 | Analisador linear sem rede perde muito LAS em pedidos curtos | Em F0/M1: treinar em UD-PT e medir em pedidos gerados | Se LAS < 80: combinar com análise pela gramática GF (a GF dá a árvore quando cobre) e reranqueamento pela abdução |
| X3 | Abdução cara | Em M5: tempo por pedido com a base real do builder | Poda por tipo antes da abdução; limite de profundidade |
| X4 | Explosão da síntese de buracos | Antes de M6: linha de base em MBPP e SyGuS com e sem PHOG, tipos, e-graph e biblioteca | Define os portões de M6. Priorizar clichês e modelo quando a síntese não alcança. |
| X5 | Reconhecimento de clichês em código real | Em M3: GRASPR simplificado sobre o builder-6 | Começar com clichês aprendidos pelo Stitch, que são sintáticos |
| X6 | Precisão das regras contra o compilador em TS | Em M3 | O compilador vira fonte de fatos, com proveniência |
| X7 | Bloqueio dos motores de busca (CAPTCHA/429) | Em M4 | Priorizar fontes estruturadas; a busca é só descoberta |
| X8 | Autoengano | Sempre | Oráculos externos, hashes, mutação |

## 15. O que abandonar do COGNITA

**Abandonar:**
- todo o `cognita/` (congelar numa tag `legacy`);
- o `TODO.txt`, que fica como histórico e **não é especificação**;
- o pagebuilder de 8 átomos: o builder-6 o substitui.

**Levar:**
- a metodologia de `audit/`: suíte adversarial, ablação e reprodução.

**No builder-6:**
- nada é removido;
- a IA entra como cliente dos comandos existentes;
- depois, comandos `ai.*` declarados no manifesto, seguindo o processo do builder (`docs/PROJECT.md`, `check:fast`).

## Verificação do plano na prática

- Cada portão gera um relatório automático no CI: métricas contra metas, hashes dos conjuntos, divergências, ablações e classificação das falhas.
- O `check:fast` e o Playwright do builder-6 têm que continuar verdes depois de cada integração.

## Primeiros passos depois da aprovação

1. Criar o repositório e mover este registro para `docs/pesquisa.md`.
2. F0:
   - semântica formal + clingo;
   - ponte sem interface para o builder-6;
   - download dos benchmarks, recursos UD/MorphoBr/GF e dados técnicos iniciais (BCD, webref, typeshed).
3. Rodar X1 e X2 (GF português e analisador linear) já em F0, porque decidem a viabilidade da linguagem.

---

> O registro da pesquisa que fundamenta este plano está em [pesquisa.md](pesquisa.md).
