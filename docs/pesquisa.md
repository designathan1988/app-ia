# Registro de pesquisa (mapa da rede)

> Documento vivo. Cada **nó** é uma técnica ou teoria encontrada, com o que resolve, a evidência, a fonte e as conexões.
> Regra permanente: **nenhum LLM**.

## Contexto fixo (do usuário)

- **Objetivo:** uma IA própria para **programar**:
  - gerar e modificar páginas e componentes no builder-6 (`C:\Codex-Shared\deepseek\builder-6`);
  - escrever código geral (HTML/CSS, JS/TS, Python), inclusive código longo e com vários arquivos;
  - entender código existente;
  - modificar e corrigir código.
- **Deve ter:** raciocínio, inferência, compreensão, aprendizado, memória, explicação. O código gerado deve ser exato e funcional.
- **Web:** busca em tempo real **sem API e sem pagar nada**. Banco de fontes, métodos, preferências e memória. Conhecimento novo só vira permanente depois de verificado.
- **Infra:** RTX 3060, Python agora e Rust depois, repositório novo. O usuário não escreve nem anota nada.
- **builder-6:** TS/React. O `DocumentJson` é a fonte da verdade. O manifesto (61 elementos, cerca de 200 propriedades, 256 comandos tipados) é declarativo. Os handlers são puros e devolvem patches. Tudo passa por `store.dispatch`, com validação a cada commit. Há importadores de HTML/CSS e cerca de 680 testes unitários e 1.333 cenários.

---

## A. Compreensão: como palavras viram entidades entendidas (não sequências decoradas)

| Nó | O que resolve | Evidência | Conexões |
|---|---|---|---|
| **Ancoragem de símbolos** (Harnad 1990) | Um símbolo só tem significado intrínseco se estiver ligado a algo fora do sistema de símbolos. | Base teórica | → A2, A5. No nosso domínio, a ancoragem é feita em **execução, renderização, manifesto e AST**, que são verificáveis. |
| **SHRDLU** (Winograd 1971) | Comandos em linguagem natural viram procedimentos sobre um modelo de mundo. Referência ("ponha *ele*"), perguntas sobre as próprias ações ("por quê?"), histórico, palavras novas por definição. | Prova de existência, sem estatística. Limites: gramática e mundo escritos à mão, mundo pequeno. | → A4, C-Rosie. O builder-6 é um "mundo de blocos" real e formal. |
| **Composicionalidade** (Frege, Montague) | O significado do todo é função das partes e da sintaxe. É isso que permite entender frases nunca vistas. | Teoria padrão da semântica formal | → A3, A6, A7 |
| **DRT** (Kamp 1981) | Entidades de discurso que persistem entre frases: anáfora e referência. | Teoria. Há reformulações composicionais (van Eijck e Kamp 1997). | → memória de sessão |
| **Interpretação como abdução** (Hobbs et al., 1993, *AI Journal*) | Interpretar = achar a **explicação de menor custo** de por que a frase seria verdadeira, dado o conhecimento, fazendo suposições quando precisa. Resolve referência, ambiguidade sintática, metonímia e compostos nominais num único mecanismo. | Projeto TACITUS (SRI) | **Nó-chave**: une linguagem, base de conhecimento e raciocínio. → motor abdutivo sobre a nossa base. |
| **Lucia / Rosie** (Lindes e Laird, Soar) | Compreensão **incremental** com Embodied Construction Grammar, ancorada em percepção, contexto e uma ontologia de ações. Reparo local de ambiguidades. | Robô que aprende tarefas por instrução | → A6, C-Rosie |
| **Gramática de construções** (ECG: Bergen e Chang; FCG: Steels) | Pares forma↔significado **bidirecionais**: a mesma gramática serve para compreender e para produzir. O limite entre vocabulário e gramática se dissolve. | FCG é uma plataforma computacional madura. Experimentos com robôs em que vocabulário e gramática emergem por "jogos de linguagem". | → geração sem molde, aprendizado de construções (B-Chang) |
| **CCG + cálculo λ** (Zettlemoyer e Collins 2005) | Aprende o léxico e a gramática semântica a partir de pares frase→forma lógica. | Superou métodos anteriores em Geo880 (880 exemplos) e ATIS | → B-Kwiatkowski. **Aprende com centenas de exemplos, não bilhões.** |
| **PRECISE** (Popescu, Etzioni e Kautz 2003) | Interface em linguagem natural **provadamente correta** para perguntas "semanticamente tratáveis". Reconhece quando não pode responder e pede paráfrase. | Mais de 80% das perguntas reais eram tratáveis e respondidas corretamente; os outros 20% foram detectados. | **Nó-chave de confiabilidade**: saber o que não entendeu. |

### A2. Análise semântica e interfaces em linguagem natural (pesquisa concluída)

| Nó | Resultado medido | Relevância |
|---|---|---|
| **GF + RGL português** (Cuconato, FGV) | Marcado como completo no quadro oficial: paradigmas, léxico, API sintática, verbos irregulares, dicionário, WordNet. Licenças: RGL LGPL-3, runtime LGPL/BSD, compilador GPL-2 (a gramática da aplicação pode ter licença livre). Não há número de cobertura em texto real, e não está confirmado se é PT-BR ou PT-PT. **ud2gf**: converte árvores UD em sintaxe abstrata GF. | **Gramática bidirecional pronta para português**: entende e gera |
| **CCG** (Zettlemoyer e Collins) | Geo880: precisão 96,25%, cobertura 79,29% (fonte secundária). Cerca de 600 pares de treino por domínio. | Aprendizado de léxico semântico |
| **SEMPRE "Overnight"** (Wang, Berant e Liang, ACL 2015) | A gramática-semente gera formas lógicas com uma frase canônica; pessoas parafraseiam. Média de 58,8% em 8 domínios. | Criar dados de treino de análise semântica **sem anotar árvores** |
| **Voxelurn**, "naturalizar uma linguagem de programação" (Wang et al., 2017) | Usuários definem novas formas de dizer em cima de uma linguagem-núcleo; em 3 dias, **85,9% dos últimos 10 mil comandos usavam sintaxe definida pelos usuários**. | **Nó-chave**: a IA aprende a linguagem natural *do usuário* por definições, crescendo a partir de um núcleo formal. É exatamente "ensinar" sem LLM. |
| **UDepLambda** (Reddy et al., 2017) | Árvores UD → formas λ, independente de língua (inglês, alemão, espanhol) | Ponte do analisador sintático para a semântica |
| **DELPH-IN / MRS** | ERG (inglês): 93,77% de cobertura, mas levou décadas. LXGram (PT-PT, 2008, licença ELDA). **PorGram** (MIT, estágio inicial, usa MorphoBr). | Mostra o custo de gramáticas de precisão |
| **COVER** (EACL 2017) | 89% de cobertura no GeoQuery, contra 77% do PRECISE | Provadores de teoremas na análise semântica |
| **Predição unânime** (Khani, Rinard e Liang 2016) | Só responde quando todos os modelos consistentes concordam: mira 100% de precisão, com ~70% de cobertura | **Abster-se em vez de errar** |
| **ACE + APE + RACE** (Attempto) | Inglês controlado → DRS/FOL/OWL. O RACE prova e **justifica em ACE**. ACE portado para GF em FR, DE, SV, FI, IT. **Não há porte para português.** | Modelo de "língua controlada + raciocínio com explicação" |
| **Metafor** (Liu e Lieberman 2005) | Histórias em inglês → esqueleto de código Python: substantivos viram objetos, verbos viram funções, adjetivos viram propriedades | Precedente de linguagem natural → estrutura de código |
| **Inform 7** | Linguagem de programação em linguagem natural, código aberto desde 2022 | Precedente |
| **ATHENA** (IBM, VLDB 2016) | Precisão 100%, 100% e 99%; cobertura de 87 a 89%, **guiado por ontologia, sem grande treino** | Ontologia = manifesto do builder / índice do código |
| **NaLIR** (VLDB 2015) | Mostra as interpretações candidatas e parafraseia de volta | Confirmação interativa |
| **SQLizer** | Analisador treinado com **só 34 consultas de livro-texto** → sketch → síntese tipada → reparo; 76 a 80% top-1, 88 a 89% top-5 | **Nó-chave**: pouquíssimo dado + síntese + tipos |
| **PRECISE**, atualização | 77,5% do GeoQuery é tratável, com 100% de precisão nessa parte. A replicação de 2015 "não replicou totalmente". | Cuidado com números antigos |

**O que todos os bem-sucedidos têm em comum:**
1. uma linguagem-alvo pequena e tipada;
2. um léxico que liga palavras a **entidades do domínio** (esquema, ontologia, índice de código);
3. candidatos podados por tipo;
4. ranqueamento por um modelo pequeno (log-linear) ou pelos próprios dados;
5. paráfrase de volta e pergunta quando há dúvida.

### A3. Recursos de português utilizáveis localmente

| Recurso | Dados | Licença / observação |
|---|---|---|
| Treebanks UD: Bosque 9.357 frases; GSD 12.020; **Porttinari 8.418 (PT-BR, notícias)**; **PetroGold 8.946 (PT-BR, petróleo)**; DANTEStocks 4.042 (PT-BR, tweets); CINTIL 38.400 (PT-PT); PUD 1.000 | Treino do analisador | Checar a licença de cada um |
| Analisadores: UDPipe 2 (LAS 84–95; **licença não comercial**); UDPipe 1 (modelo de 16 MB); Stanza (LAS 80–93); Portparser (Porttinari); LX-Suite (99% POS) | Todos são redes neurais pequenas. **Decisão: treinar nosso próprio analisador por transições com modelo linear** (perceptron médio), sem rede neural, e usar esses números como referência. | — |
| PALAVRAS (Bick) | 50 mil lemas, ~5 mil regras, >99% POS | **Comercial**; o motor CG-3 é GPL |
| **MorphoBr** (Apache-2.0, FST com Foma); DELAF-PB (~880 mil formas) | Morfologia exata | — |
| OpenWordNet-PT (CC BY 4.0); PropBank.Br (1.453 sentidos); VerbNet.Br (257 classes) | Semântica lexical e quadros verbais | — |
| Corref-PT (182 textos); CORP (resolvedor de correferência por regras) | Correferência | — |
| **UGCNormal** | Normalização de texto informal PT-BR por léxico + fonética | "vc", "pq", "tá" |
| Aviso | Nem LLMs escapam: NL2SQL cai de 47% em inglês para 40% em PT-BR | O português exige cuidado próprio |

### A4. Diálogo e geração

| Nó | Uso |
|---|---|
| **TrindiKit / GoDiS** (estado de informação, perguntas em discussão, acomodação) | Gerenciar a conversa: o usuário dá as informações em qualquer ordem |
| **OpenDial** (regras probabilísticas) | Alternativa |
| **Esclarecimento** (Quintano e Rodrigues 2007, **em português**) | Perguntar **só quando a ambiguidade muda a resposta**; escolher a pergunta por ganho de informação esperado |
| **Linearização GF** | Gerar a paráfrase de confirmação ("Entendi: renomear `X` para `Y` em 3 arquivos. Confirma?") |
| **SimpleNLG-BP** (INLG 2014) | Realização de texto em PT-BR |
| **Explicação de provas** (RACE, PROVERB, P.rex) | Explicar o raciocínio em português a partir da árvore de derivação |

### A5. Arquiteturas cognitivas: estado real

- **NARS / ONA** (MIT, C): aprendizado procedural. Não tem capacidade demonstrada em linguagem ou código; o próprio README aponta um LLM para a entrada em inglês. **Experimental, apenas para crenças revisáveis.**
- **AERA:** o agente S1 aprendeu diálogo multimodal em tempo real observando humanos (entrevista simulada). Não foi testado em código.
- **Soar / Rosie:** aprendeu mais de 60 jogos e tarefas por instrução em inglês restrito. **É a demonstração mais relevante de aprendizado por instrução.**
- **OpenCog Hyperon:** pré-alfa. **Sigma:** prova de conceito.

## B. Aprendizado sem LLM: viés indutivo, aquisição, generalização

| Nó | O que resolve | Evidência | Conexões |
|---|---|---|---|
| **A necessidade de viés** (Mitchell 1980) | Generalizar exige viés: conhecimento do domínio, uso pretendido, simplicidade, **analogia com o já aprendido**. Consistência com os dados nunca basta (espaço de versões). | Fundamento teórico | → B-MDL, B-ILP. O viés é **explícito e projetado**, não emergente. |
| **MDL / Occam / Solomonoff** | Escolher a hipótese que minimiza L(H) + L(D\|H). Evita sobreajuste sem precisar de validação separada. | Teoria da informação algorítmica | → Stitch, MaxSynth, BPL |
| **ILP / Popper** (Cropper e Morel 2021) | Aprende programas lógicos (inclusive recursivos) a partir de exemplos positivos e negativos mais conhecimento de fundo. Ciclo gerar → testar → **aprender restrições com a falha**. | Supera outros ILPs em acurácia e tempo | → MaxSynth (dados ruidosos, MDL), Combo |
| **Meta-interpretive learning / Metagol** (Muggleton) | Invenção de predicados e recursão por abdução num meta-interpretador. Aprende de **um exemplo** com viés de domínio incremental. | Transformações em planilha com um exemplo | → biblioteca, one-shot |
| **Bayesian Program Learning** (Lake, Salakhutdinov e Tenenbaum, *Science* 2015) | Conceitos como programas. Aprendizado com **um exemplo**, em nível humano. | Superou deep learning na tarefa | → B-PLoT |
| **Linguagem do pensamento probabilística** (Goodman e Tenenbaum) | Conceitos são programas probabilísticos compostos como linguagem, e generalizam como humanos. | Evidência experimental em aprendizado de conceitos | → representação de conceitos de design e de código |
| **DreamCoder** (Ellis et al., PLDI 2021) | Biblioteca de abstrações aprendida (refatoração por e-graph) mais política de busca, em ciclo wake-sleep. | 8 domínios; resolve mais e mais rápido | A rede de reconhecimento dele é opcional; usar a versão sem rede. → Stitch |
| **Stitch** (Bowers et al., POPL 2023) | Aprendizado de biblioteca por compressão de cima para baixo. | 1.000 a 10.000× mais rápido e 100× menos memória que o DreamCoder, com qualidade igual ou melhor. Código aberto (Rust e Python). | **Nó-chave**: aprender componentes e funções reutilizáveis do código do usuário. |
| **Euphony / PHOG** (Lee et al., PLDI 2018) | Gramática probabilística de ordem superior estimada **por contagem** a partir de soluções conhecidas, usada para ordenar a busca de síntese. | Ganho significativo sobre sintetizadores SyGuS | **Substitui qualquer "ranqueador neural"**: é estatística simbólica, pequena e explicável. |
| **Getafix** (Facebook) | Padrões de correção mineirados de pares antes/depois por anti-unificação e agrupamento hierárquico. | Em produção industrial (SapFix, Infer) | → reparo |
| **EBL / chunking** (Soar) | Uma resolução bem-sucedida vira regra nova. Aprende de um exemplo com teoria do domínio. | Décadas de uso no Soar | → aprender procedimentos de edição no builder por demonstração |
| **Rosie / aprendizado interativo de tarefas** | Aprende tarefas hierárquicas por instrução em linguagem natural. Pergunta quando há ambiguidade. Transfere entre tarefas. | Código aberto (BSD); aprende de um episódio | → "ensinar a IA em português" |
| **L\* / LearnLib / AALpy** | Aprendizado ativo por consultas e contraexemplos até o modelo ficar exato. | Padrão de pesquisa em aprendizado de modelos | → desambiguação por contraexemplo, modelar APIs caixa-preta |
| **SME / analogia** (Forbus e Gentner) | Mapeamento estrutural entre situações relacionais; transferência de solução. | O único mapeador de analogias em software implantado | → "faz igual àquele" |
| **Copycat** (Hofstadter e Mitchell) | Analogia com conceitos fluidos (slipnet, workspace, codelets); percepção de alto nível. | Micro-domínio | Referência teórica; avaliar para percepção de padrões de design |
| **Raciocínio baseado em casos** | Recuperar e adaptar soluções anteriores. | Déjà Vu, CAESAR. A adaptação é o ponto difícil. | → junto com SME e síntese para adaptar |
| **NARS / ONA** (Pei Wang) | Crenças revisáveis com confiança, sob conhecimento e recursos insuficientes, em tempo real. | Estudos de 2024 com condicionamento operante | → modelo de crença para preferências e fontes da web |
| **Aprendizado de palavras entre situações** (Siskind 1996; Yu e Smith 2007) | Aprende o significado de palavras pela coocorrência consistente com referentes em várias situações. | Algoritmos e experimentos humanos | → aprender vocabulário do usuário pelo uso (fala + ação na interface) |
| **Aquisição sintaxe+semântica** (Kwiatkowski et al., 2012) | Aprende uma gramática CCG e o significado das palavras a partir de frases pareadas com significados possíveis ("fast mapping"). | Supera parser semântico no CHILDES | → aprender a linguagem do domínio a partir de pares (pedido, ação executada) |
| **Construções emergentes** (Chang 2009, ECG) | Aprende construções forma↔significado pelo uso em contexto; o contexto resolve o input pobre. | Modelo computacional de aquisição | → idem |

## C. Raciocínio e arquitetura cognitiva

| Nó | Papel | Evidência |
|---|---|---|
| **Common Model of Cognition** (Laird, Lebiere e Rosenbloom 2017) | Estrutura consensual: memória de trabalho, memória procedural, memória declarativa, percepção e ação, metacognição. | Consenso entre Soar, ACT-R e Sigma. Esqueleto de alto nível da nossa arquitetura. |
| **Soar** | Espaços de problema, impasse → sub-objetivo, chunking, memórias semântica e episódica. | Base do Rosie |
| **Datalog / ASP (clingo)** | Raciocínio declarativo, planejamento, otimização, restrições. clingo é o sistema de ASP mais usado (aterramento + resolução tipo SAT). | Maduro; plingo cobre o caso probabilístico |
| **Cyc** | Base de senso comum com cerca de 1,5 milhão de asserções, motor de inferência, **microteorias** para contextos contraditórios. | Lição: conhecimento feito à mão não escala. Microteorias = contextos isolados (→ ramos da nossa base). |
| **Abdução ponderada** (Hobbs) | Inferência para a melhor explicação, unindo compreensão e raciocínio. | Ver A |

## D. Geração de conteúdo e de código sem LLM

| Nó | O que gera | Evidência |
|---|---|---|
| **FlashFill / PROSE** | Programas de 10 a 20 linhas a partir de exemplos. | Excel 2013+, centenas de milhões de usuários |
| **InferUI** (Bielik et al., OOPSLA 2018) | Layouts relacionais robustos a partir de exemplos, com um modelo probabilístico de restrições. | 100% num único dispositivo; 92% das views generalizam para outros tamanhos de tela, em apps reais (top 500 do GitHub e da Play Store) |
| **Mockdown** (Lukes et al., FSE 2021) | Layout web (restrições) sintetizado a partir de exemplos. | Números a extrair do artigo |
| **GRIDS** (Dayama et al., CHI 2020) | Layouts em grade gerados por **programação linear inteira mista** (alinhamento, empacotamento, agrupamento, preferências). | Estudos com designers |
| **Cassowary** (Badros e Borning) | Restrições lineares incrementais (simplex dual), requisitos e preferências. | É a base do Auto Layout da Apple; portas para JS e Python |
| **ASP para geração procedural** (Smith e Mateas 2011) | Descrever o **espaço de projeto** declarativamente e gerar artefatos com solver genérico. | Referência em geração procedural |
| **Cassius / VizAssert** (Panchekha e Torlak, OOPSLA 2016) | CSS formalizado em SMT; verifica propriedades de layout em vários tamanhos de tela. | Verificação formal de layout web |
| **Sketch-n-Sketch** | Edita a saída (SVG) e sintetiza a mudança correspondente no programa. | Edição bidirecional |

### D1. Síntese de programas (pesquisa concluída)

**Constatação geral:** os sucessos publicados são funções ou expressões de ~5 a 100 nós de AST, resolvidas em segundos ou minutos. **Nenhum sintetizador gera sozinho uma aplicação com vários arquivos.**

| Nó | O que gera | Evidência | Uso |
|---|---|---|---|
| **Synquid** (PLDI 2016) | Funções recursivas a partir de tipos refinados. | 64/64 benchmarks do artigo, a maioria em menos de 5 s (ordenações, árvores rubro-negras). A especificação é cerca de 6× menor que o código. | Síntese dedutiva guiada por tipos |
| **SuSLik / Cypress** (POPL 2019, PLDI 2021) | Código de ponteiros a partir de lógica de separação. | Menos de 1 s na maioria dos casos | Referência dedutiva |
| **Stainless** (EPFL) | Verificação e síntese em subconjunto de Scala, traduzido para C. | Sistema de arquivos do Solar Orbiter (~1.000 linhas) | — |
| **KIDS / Specware** (Kestrel) | Algoritmos derivados de especificações formais. | Escalonadores militares em uso real | Derivação por refinamento |
| **FlashMeta / PROSE** | Programação por exemplos sobre uma DSL. Os exemplos são propagados de trás para frente por funções-testemunha. | Excel, PowerShell | O SDK é **não comercial** → implementar o algoritmo nós mesmos |
| **Myth / Smyth / Burst** (POPL 2022) | Funções recursivas por tipos e exemplos. | Burst: 43/45 benchmarks | — |
| **λ²** (PLDI 2015) | Programas map/fold, **o mais simples** que satisfaz os exemplos. | — | Garantia de minimalidade |
| **SyPet / Hoogle+ / Hectare** | Composição de chamadas de API por tipos (redes de Petri, autômatos). | SyPet: 25/30 tarefas reais. Hoogle+: +50% de tarefas no estudo com usuários. | **Composição de APIs de bibliotecas TS/Python** |
| **Morpheus** (PLDI 2017) | Pipelines de dados (R) a partir de tabelas-exemplo, com dedução SMT. | — | Transformações de dados |
| **Absynthe** (PLDI 2023) | Busca guiada por domínios abstratos definidos pelo usuário, validada **executando na linguagem real**. | Compete no SyGuS e iguala o AutoPandas (deep learning) em pandas | **O modelo mais próximo para JS e Python** |
| **Solvers SyGuS** (cvc5, EUSolver) | Expressões a partir de gramática e especificação. | SyGuS-Comp 2017: EUSolver 407/569. Estudo de 2026: ferramentas simbólicas superaram o Qwen-32B e igualaram ou superaram o GPT-5 em síntese formal. | cvc5 (BSD) para os buracos |
| **Sketch / CEGIS / Rosette** | Programa com buracos preenchidos por SMT, num laço de contraexemplos. | Rosette tem manutenção ativa | Buracos pequenos |
| **egg / Ruler / babble** | E-graphs para saturação de igualdades. babble aprende bibliotecas módulo teoria equacional. | babble tem melhor compressão e é ordens de grandeza mais rápido | Equivalência, poda, biblioteca |
| **Stitch** | Biblioteca por compressão, puramente simbólica. | Ver B | — |

### D2. Correção por construção (código exato de verdade)

| Nó | Evidência | Uso |
|---|---|---|
| **Dafny** (compila para JS, Python, C#, Java, Go) | A AWS reconstruiu o motor de autorização em Dafny e gerou Java; em produção em 2024, sem incidentes e 3× mais rápido. No Cedar, o modelo Dafny tem 1/6 do tamanho do código Rust de produção, com cerca de 100 milhões de testes diferenciais. | **Núcleos de lógica exata compilados para JS e Python** |
| **F\* / HACL\*** | Criptografia verificada no Firefox, no Linux e no Signal | Custo altíssimo; referência |
| **Coq / Fiat / CompCert** | CompCert: nenhum bug de código errado encontrado no núcleo verificado depois de ~6 anos-CPU de testes aleatórios | — |
| **B / Event-B** | Linha 14 do metrô de Paris: 86 mil linhas de Ada geradas, nenhum bug relatado depois da prova | Refinamento por etapas |
| **Ur/Web** (POPL 2015) | Tipos garantem que não há injeção, HTML inválido, link interno quebrado nem formulário incompatível com o handler, **mesmo em código gerado** | **Precedente para "gerar web que não pode dar errado"** |

### D3. Código longo e com vários arquivos

| Nó | Evidência | Uso |
|---|---|---|
| **Geração a partir de modelo** (JHipster JDL, Xtext/Xtend, EMF, JetBrains MPS) | Um arquivo de modelo gera o back-end e o front-end inteiros, consistentes entre arquivos. mbeddr (MPS) é uma IDE industrial de C. | **É o que mais gera código com garantia estrutural** |
| **Pesquisa na indústria** (Whittle et al., IEEE Software 2014, 450 profissionais) | MDE funciona com DSLs feitas para partes-chave; o ganho de geração supera o custo de integração | Usar DSLs, não "gerar tudo" |
| **Decomposição** (hierárquica do Mockdown, especificações do Synquid, refinamento do Fiat/Specware, HTN/SHOP2) | Nenhum sistema HTN → código-fonte com benchmark publicado | **Lacuna** a preencher por nós |
| **HTN-Maker / ND-HTN-Maker** | Aprende métodos HTN a partir de demonstrações em tempo polinomial, de forma correta (sound) | → aprender "como construir X" com os exemplos do usuário |

### D4. Reparo automático (pesquisa concluída)

| Nó | Resultado | Lição |
|---|---|---|
| GenProg | 55/105 "reparados", mas só **2/105 corretos** numa auditoria posterior | Reparo guiado só por testes sobreajusta |
| Prophet | 15 a 18 corretos de 69 | Modelo de "código correto" ajuda |
| **Angelix / SemFix** | Execução simbólica + SMT; reparos de várias linhas; o primeiro Heartbleed corrigido automaticamente | Funciona quando há especificação ou oráculo |
| **TBar** | 43 corretos no Defects4J (74 com localização perfeita) | Templates são o método simbólico mais forte |
| **Getafix / SapFix** | A correção humana fica em 1º lugar entre 12% e 91% das vezes; 165 patches em 90 dias | Padrões mineirados funcionam em produção |
| RepairThemAll (2019) / estudo do QuixBugs | 21% com patch; no QuixBugs, 53% dos patches sobreajustam | **Nunca aceitar um patch só porque os testes passam** |

### D5. Verificação automática (base da "exatidão")

| Nó | O que faz | Uso |
|---|---|---|
| **CrossHair** (Python) | Execução simbólica + SMT sobre contratos e anotações de tipo. Acha contraexemplos, gera testes, compara o comportamento de duas funções. Integra com o Hypothesis. | **Verificar código Python gerado sem escrever testes** |
| **Pynguin** | Gera testes unitários Python por algoritmo evolutivo (DynaMOSA): 68% de cobertura de ramos em média em módulos reais | Testes automáticos para o código gerado e para o legado |
| Hypothesis / fast-check (o builder-6 já usa fast-check) | Testes baseados em propriedades | Propriedades derivadas da especificação |

### D6. Compreensão de código (pesquisa concluída)

| Nó | Evidência | Uso |
|---|---|---|
| **CodeQL** (QL → Datalog) | Milhões de linhas. Para linguagens compiladas, observa o compilador real durante o build. | Modelo de base de fatos de código |
| **Doop / Soufflé** | Points-to em Datalog, 15× mais rápido que o estado da arte anterior | Motor Datalog compilado |
| **Glean** (Meta) | Fatos de código com a linguagem Datalog Angle | — |
| **IncA / DRedL** (OOPSLA 2018) | Análises incrementais que atualizam em milissegundos | **Incremental por edição** |
| Precisão | Só é tão precisa quanto os fatos extraídos. Para TS e Python, **usar os fatos do próprio compilador** (TypeScript checker, pyright). | Decisão confirmada |

### D7. Linguagem natural + síntese, sem LLM (pesquisa concluída)

| Nó | Resultado |
|---|---|
| **SmartSynth** (MobiSys 2013) | Mais de 90% de 640 descrições viram o script certo |
| **NLyze** (SIGMOD 2014) | 94% top-1 e 97% top-3 em 3.570 descrições de planilha |
| **Desai et al.** (ICSE 2016), NL → DSL genérico | 80% top-1 e 90% top-3 em mais de 1.200 descrições |
| **SQLizer** (OOPSLA 2017) | Análise semântica → completar sketch por tipos → reparo; 78% top-1, 90% top-5 |
| **AnyCode** (OOPSLA 2015) | Inglês e Java misturados → expressões Java |

**Padrão:** a alta acurácia só aparece **dentro de uma DSL tipada**, com uma lista ranqueada de candidatos e confirmação do usuário.

### D8. Programação por demonstração

| Nó | O que faz |
|---|---|
| **SUGILITE** (Li e Myers) | Instrução verbal + demonstração + hierarquia da interface → script **generalizado a partir de uma demonstração**, com parâmetros e variações |
| **Ringer / Rousillon / WebRobot** | Automação web por demonstração; WebRobot é interativo (PLDI 2022). Limite: programas web complexos demais travaram o avanço da área. |

### D9. Aprendizado autônomo

| Nó | O que faz |
|---|---|
| **AERA** (Thórisson, 2020) | Aprendizado organizado em **relações causais** partindo de correlações observadas, com modelos relacionais finos e raciocínio "micro-ampliativo". Transfere entre tarefas sem ajuda externa (robô que manipula objetos e produz frases corretas) e sem ML clássico nem aprendizado por reforço. Referência para modelos causais de "ação → efeito" no builder. |

### Limites honestos (da pesquisa)

- **Falha em:** inglês ou português aberto sem uma DSL; busca que explode acima de algumas dezenas de nós por buraco; especificações caras de escrever (seL4 precisou de ~20:1 de prova por código); reparo guiado só por testes sobreajusta; nenhum senso comum de design ou de texto; o custo inicial de construir DSLs e geradores é grande.
- **É estritamente melhor que um LLM em:** correção provável contra uma especificação; determinismo; minimalidade; segurança por construção; análise incremental em milissegundos; síntese formal (simbólico ≥ GPT-5 no estudo de 2026); gerar milhares de linhas consistentes a partir de um modelo, sem alucinação.

### D10. Programação baseada em conhecimento e qualidade de design

| Nó | O que resolve | Evidência | Uso |
|---|---|---|---|
| **Programmer's Apprentice / KBEmacs** (Rich e Waters, MIT) | Programar **compondo "clichês"** (algoritmos e estruturas estereotipados) com o *Plan Calculus*. O programador dá comandos de alto nível e o sistema monta o código. | A série de comandos chega a ser **uma ordem de grandeza mais curta que o programa**. Operou sobre Ada e Lisp de tamanho realista. | **Nó-chave**: preenche a lacuna "decomposição → código". Clichês = biblioteca de planos de programa (aprendida por Stitch e minerada do código). |
| **GRASPR** (Wills, MIT 1992) | **Reconhece clichês** no código por *parsing* de gramática de grafos e reconstrói a descrição hierárquica do design. Tolera variações de implementação. | Tese e artigos | **Entender código = reconhecer planos**: "isto é um debounce", "isto é paginação" |
| **Métricas de estética de interface** (Ngo et al.) | 14 medidas formais: equilíbrio, simetria, alinhamento, proporção, densidade, ritmo, ordem, entre outras | Aplicadas a páginas web | Critério objetivo de "página bonita" |
| **Otimização combinatória de interfaces** (Oulasvirta, Aalto) | O layout vira programa inteiro, e a função objetivo vem de modelos preditivos de desempenho humano | Linha de pesquisa com GRIDS | Gerar páginas **boas**, não só válidas |

## E. Web sem API e banco de conhecimento (pesquisa concluída)

**Busca sem API e sem custo:**
- **SearXNG local** (AGPL, Docker): metabusca com JSON (ativar em `settings.yml`, com o limitador desligado no localhost). Consulta Brave e DDG, mais Stack Overflow, GitHub, PyPI, Docker Hub e npm. Os motores são suspensos automaticamente quando dão CAPTCHA ou 429. **Escolha principal.**
- **YaCy** (GPL): um crawler e índice próprio para uma lista branca de domínios de documentação.
- **Não usar:** DDG direto (zona cinzenta de termos de uso), Mojeek e Brave (o robots.txt bloqueia a busca), Google (os termos proíbem).
- **Regras** (RFC 9309):
  - robots.txt com cache de até 24 h;
  - User-Agent identificado;
  - um host por vez, com atraso;
  - GET condicional (ETag);
  - cache local;
  - a busca serve só para descobrir URLs; o conteúdo vem da fonte primária.

**Fontes estruturadas e exatas, sem chave** (o coração do conhecimento atualizado):

| Fonte | Tamanho medido | Licença | Atualização |
|---|---|---|---|
| MDN browser-compat-data (suporte e depreciação por navegador) | 20,4 MB | CC0 | semanal |
| w3c/webref (IDL do DOM, gramáticas CSS, elementos, eventos) | ~2 MB | MIT | crawl a cada 6 h / npm semanal |
| web-features (status Baseline) | 4,8 MB | Apache-2.0 | npm |
| caniuse-lite | 1,5 MB | CC BY 4.0 | ativo |
| TypeScript 6.0.3 `lib.*.d.ts` (**o TS 7.0 em Go ainda não tem API estável → extrair com o 6.x**) | 24,3 MB | Apache-2.0 | — |
| DefinitelyTyped `@types/*` | por pacote | MIT | ~1 h depois do merge |
| typeshed (stubs Python 3.10–3.14) | 33,7 MB | Apache/MIT | até diário |
| Python docs + `objects.inv` (índice canônico símbolo → URL) | 5–13 MB | PSF / exemplos 0BSD | contínuo |
| DevDocs (836 conjuntos; o núcleo web + Python fica em ~139 MB; frameworks populares ~62 MB) | 8,7 GB no total | por conjunto | `mtime` por conjunto |
| npm registry (packument JSON, feed de mudanças `_changes`) | react = 7 MB | — | tempo real |
| PyPI JSON + RSS | pequeno | — | tempo real |
| OSV (vulnerabilidades npm/PyPI, delta `modified_id.csv`) | — | misto | contínuo |
| deps.dev (grafo de dependências, sem chave, cache permitido) | — | — | — |
| mdn/content (markdown) | 509 MB com histórico | Prosa CC BY-SA 2.5; exemplos CC0 | diário |
| Stack Exchange dump | 98 GB | CC BY-SA com condição extra | opcional |

- **GitHub anônimo:** 60 requisições/hora; clones e `raw` também são limitados. Usar tarballs do npm/PyPI e jsDelivr como alternativa.

**Conhecimento de API em fatos exatos:**
- TS: API do TypeScript 6 / ts-morph → símbolos, assinaturas, sobrecargas, `@deprecated`. O API Extractor gera relatórios de API que podem ser comparados para achar quebras.
- DOM: webidl2 sobre `@webref/idl`.
- CSS: css-tree sobre a sintaxe do `@webref/css` (**gramática exata dos valores**).
- Suporte: `__compat` do BCD + Baseline.
- Python: typeshed via `ast` / griffe (`griffe check` detecta quebras de API entre versões), stubtest, `objects.inv`.
- **O sinal mais confiável de mudança** é o diff da superfície de API entre versões, mais que o changelog.

**Base local:**
- SQLite (WAL) + FTS5: `bm25` com pesos, tokenizador trigram para identificadores, external-content.
- Blobs por SHA-256.
- Extração de texto: trafilatura (Apache-2.0) ou Readability + DOMPurify. Arquivamento: ArchiveBox (MIT).
- Esquema: `source`, `document`, `doc_fts`, `symbol`, `compat`, `package_version`, `api_diff`, `claim` (com `superseded_by`), `preference`, `memory`, `sync_state`.
- Pipeline:
  - a cada 6 h: npm da lista de observação;
  - diário: PyPI RSS, OSV, `git fetch` de typeshed, MDN e webref;
  - semanal: BCD, webref, web-features, `@types`, DevDocs.
- **Espelho útil do núcleo: ~1–2 GB** de *dados* (não de modelo).

**Segurança:**
- Todo conteúdo buscado é dado não confiável.
- Execução de código só em sandbox real (gVisor/microVM, ou Deno sem permissões). **Pyodide não é fronteira de segurança.**
- Licença SPDX por trecho (ScanCode). Preferir fontes CC0/MIT/0BSD para reuso literal.
- **Nunca sugerir pacote sem verificar** nome e versão no registry local, idade, downloads e OSV.
- Afirmações que não vêm de fonte estruturada exigem **duas fontes independentes**.

---

## Conexões emergentes (hipóteses de arquitetura)

1. **Compreender = abdução sobre a base de conhecimento.** A frase vira uma forma lógica (gramática de construções ou CCG). A interpretação é a explicação de menor custo contra o documento, o código e o conhecimento (Hobbs). Se nenhuma interpretação passa do limiar de custo, o sistema pede paráfrase ou esclarecimento (PRECISE).
2. **Ancoragem por execução.** Palavras e construções mapeiam para comandos do builder, entidades da AST e restrições de layout verificáveis (Cassowary, geometria renderizada). O significado de uma palavra é o que o sistema **faz e verifica** com ela (SHRDLU, Harnad).
3. **Gramática bidirecional** (FCG/ECG). O mesmo conhecimento serve para compreender e para gerar respostas. Não há molde.
4. **A linguagem é aprendida por pares (pedido, ação verificada)** (Kwiatkowski, Chang, aprendizado entre situações, Rosie). Cada uso bem-sucedido refina o léxico e as construções, e o usuário ensina sem escrever nada formal.
5. **Viés indutivo explícito** (Mitchell), com três fontes:
   - tipos e o manifesto (conhecimento do domínio);
   - MDL (simplicidade);
   - biblioteca aprendida (analogia com o já aprendido).
6. **Geração de código = busca guiada** por gramática probabilística aprendida por contagem (Euphony) + biblioteca (Stitch) + restrições (ASP, MILP, Cassowary para layout) + verificação.
7. **Contextos isolados** (microteorias do Cyc) = ramos da base: projeto, sessão, hipótese.
8. **O builder-6 já É uma DSL tipada.** O manifesto dele (elementos, propriedades, comandos tipados, modelo de conteúdo) é exatamente a "DSL tipada + gerador determinístico" que, pela pesquisa, dá alta acurácia a linguagem natural → programa (padrão SmartSynth/NLyze/SQLizer: 80–94% top-1) e gera muito código consistente (padrão MDE). **Estratégia central:** a IA opera sobre modelos e DSLs tipadas; os geradores produzem os arquivos; a síntese preenche só buracos locais; a verificação fecha o ciclo.
9. **Para código geral** (fora do builder), aplicar a mesma receita:
   - modelos e DSLs do projeto (entidades, rotas, componentes, dados) → geradores com vários arquivos;
   - síntese local por tipos, exemplos e contratos (Absynthe, SyPet, λ², cvc5);
   - lógica crítica em Dafny compilado para JS e Python;
   - verificação por CrossHair, Pynguin e fast-check, mais typecheck.
10. **"Exato e funcional" = exato contra uma especificação verificada.** Estrutura, tipos e segurança ficam garantidos por construção. O comportamento fica garantido na medida da especificação: contratos, propriedades, testes gerados e exemplos. Quando falta especificação, a IA **a obtém**: pergunta, pede exemplo, deriva do contexto.
11. **Aprender a construir** por demonstração e instrução (SUGILITE, HTN-Maker, Rosie). O usuário faz uma vez ou explica, e a IA vira isso em método reutilizável e generalizado.

## Nós a explorar em seguida (a pesquisa continua durante a execução)

**Pesquisas concluídas e registradas acima:** síntese, correção por construção, vários arquivos, reparo, compreensão de código, linguagem natural + síntese, português, diálogo, geração, web e banco, AERA, HTN-Maker, SUGILITE/Ringer, CrossHair/Pynguin, Programmer's Apprentice, GRASPR, estética de layout.

**Próximos nós:**
- Plan Calculus em detalhe (representação de clichês)
- PROSE/FlashMeta: o algoritmo de funções-testemunha, para implementar o nosso
- Voxelurn: como as definições dos usuários generalizam
- GF-Por: variante PT-BR e cobertura real
- Abdução eficiente: ILP abdutiva, Phillip/Henry (abdução por ILP de Inoue)
- Métodos formais leves para JS (Cassius, verificação de CSS)
- Modelos de design de interface (Material, heurísticas de Nielsen formalizadas)
- Aprendizado de construções com pouco dado (FCG)
- Execução simbólica para JS (ExpoSE)

**Lista anterior:**

- A pesquisa em andamento: síntese dedutiva (Synquid, SuSLik), sintetizadores SyGuS, reparo semântico (Angelix), correção por construção (Dafny compila para JS e Python), MDE/JHipster para vários arquivos, SQLizer/SmartSynth (linguagem natural + síntese).
- A pesquisa em andamento: recursos de português (PALAVRAS, UD, GF-Portuguese, dicionários), NARS/AERA, gerenciamento de diálogo.
- A pesquisa em andamento: SearXNG e YaCy (busca sem API), registries npm/PyPI, `.d.ts`/typeshed/webref como conhecimento exato de APIs, SQLite FTS5.
- **Próximos por mim:**
  - AERA (Thórisson): aprendizado autônomo de modelos causais;
  - OpenCog Hyperon/MeTTa: estado real;
  - Sigma (Rosenbloom);
  - HTN (SHOP2) para decompor tarefas de programação;
  - planejamento de programas com várias partes;
  - "programming by demonstration" para interfaces web (Sugilite, Rousillon);
  - aprendizado de construções a partir de pouco dado (FCG);
  - geração de linguagem com gramática reversível em português;
  - e-graphs (egg);
  - execução simbólica para compreender e testar código;
  - geração de testes (Hypothesis, EvoSuite, Pynguin) como verificação automática da "exatidão".
