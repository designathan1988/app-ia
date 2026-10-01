# Plano D: compreensão aprendida e medida fora de mim

> **Em vigor desde 2026-10-01: [roteiro CCG](roteiro_ccg.md).** Mapeamento aprendido da língua: CCG, léxico induzido (UBL/FUBL) e aprendizado pela execução. Objetivos O1 a O6, etapas E0 a E6, com prazos. A §7 abaixo (A1–A4) foi substituída por ele.

> **Revisado em 2026-10-01 pela [auditoria](auditoria.md).** As etapas D2 a D5 da §5 foram substituídas pela §7: gerar todas as ações possíveis e ranquear com um modelo log-linear aprendido. O motivo: a etapa frase → ação não aprendia de nenhum dado.

Este plano substitui o [plano da compreensão](plano_compreensao.md) (etapas C0 a C6). O plano anterior fica como
registro histórico. A forma lógica, a ancoragem e a abdução que ele construiu continuam sendo a base. O que muda é
**de onde vem o conhecimento e como se mede**.

## 1. Por que a abordagem anterior não converge (2026-10-01)

**A medida limpa não sobe.** Cada rodada nova, antes das correções, acerta mais ou menos o mesmo:

| Rodada | r8 | r9 | r10 | r11 | r12 | r13 |
|---|---|---|---|---|---|---|
| Medida limpa | 63% | 82% | 46% | 70% | 52% | 75% |

É o padrão das rodadas 3 a 6 do motor antigo (17 a 22 de 30), agora numa arquitetura melhor. O congelado v6 passou
com 0 errados, mas só depois de cinco ciclos de congelado → rodada → correção.

**Causas**
1. **Rodada por classe ainda é remendo.** Cada rodada acha "classes" novas, e cada classe vira uma regra escrita à
   mão. Exemplos: "'o texto X' é o elemento que mostra X", "light gray × gray", "o núcleo copular é o atributo". A
   língua tem cauda longa: a lista de classes não termina.
2. **Os pesos são inventados.** `interpret.py` e `ground.py` têm dezenas de constantes de custo ajustadas à mão
   (`TIE`, `UNLIKELY`, `CONSTRUCTION`, `LABEL_SPLIT`, ...). Uma abdução por custo só generaliza com custos
   aprendidos de dados.
3. **O significado dos verbos é uma tabela minha** (`STATE_OF_FRAME`, listas fechadas do perfil). Existem recursos
   externos que descrevem isso para milhares de verbos: PropBank, VerbNet e FrameNet em inglês; PropBank.Br,
   VerbNet.Br e FrameNet Brasil em português.
4. **O analisador sintático é fraco** (guloso, LAS ~80 pt e ~75 en). Tudo o que vem depois herda os erros dele, e
   `alternatives.py` existe para tapar esses buracos.
5. **Eu escrevo as frases de teste.** Os conjuntos são pequenos (20 a 88 itens) e saem da minha imaginação. O motor
   aprende o meu jeito de escrever, não a língua. "Congelado" não é "externo".

## 2. A meta, definida de forma mensurável

"Entender toda a linguagem" tem três camadas:
- **Estrutura:** em qualquer frase pt ou en, quem fez o quê a quem, onde, como. Medida em anotação humana externa
  (treebanks UD, PropBank).
- **Ação:** o estado correto do documento para todo pedido que se ancora no que a máquina sabe fazer. Medida em
  pedidos escritos por outras pessoas.
- **Segurança:** todo o resto vira pergunta, recusa ou fato registrado, nunca uma ação errada. Medida em frases
  fora do domínio.

**"Sem mais ajustes" quer dizer:** uma falha nova se resolve com dados, com um recurso lexical ou com ensino na
conversa, **nunca com uma regra nova no código.**

## 3. Regras deste plano

1. **Nenhuma regra nova de construção** em `interpret.py`, `ground.py`, `logic_form.py` ou `alternatives.py`. Se
   um erro só se resolve com regra, a etapa que falta é a que deve ser construída.
2. **A medida principal é externa:** frases escritas por outras pessoas, julgadas por oráculos mecânicos. As rodadas
   e os congelados autorais (r7 a r13, v1 a v6) e o M5 passam a ser só testes de regressão.
3. **Partes separadas:** treino, desenvolvimento e teste. O teste só é medido nos portões. Toda medida é registrada
   limpa (antes de qualquer mudança).
4. **Modelos treinados sim, LLM nunca.** Modelos lineares ou estatísticos por contagem, pequenos e locais, treinados
   aqui em anotação humana pública: o analisador, o rotulador de papéis e os pesos da abdução. Nada neural, nenhum
   modelo de linguagem pré-treinado, de nenhum tamanho.
5. **CPU:** prioridade abaixo do normal e um trabalho pesado por vez.

## 4. Conjuntos externos

| Camada | Conjunto | Língua | Oráculo |
|---|---|---|---|
| Estrutura | UD Bosque, Porttinari e PetroGold (teste) | pt | árvores humanas: UAS e LAS |
| Estrutura | UD EWT (teste) | en | árvores humanas: UAS e LAS |
| Estrutura | Universal Propositions 2.0: EWT (ouro), Bosque (projetado, prata) | en, pt | papéis PropBank: F1 de argumentos |
| Ação | DocEdit-PDF (Mathur et al., AAAI 2023): pedidos de edição escritos por pessoas, com o comando executável | en | tipo de ação, componente e atributos do comando |
| Segurança | MASSIVE 1.1 (Amazon): frases de assistente, pt-PT e en-US, paralelas | pt, en | nada se refere à página: **qualquer alteração executada é um erro** |

**Lacuna conhecida:** não há conjunto público de pedidos de edição escritos por pessoas em português. Uma etapa
própria procura fontes humanas. Nada traduzido por máquina entra como medida.

## 5. Etapas

| Etapa | Entrega | Portão |
|---|---|---|
| **D0** | Conjuntos externos baixados e convertidos (`experiments/externo/`). Mapeamento DSL do DocEdit → estados do builder, feito uma vez no vocabulário da DSL, nunca frase a frase. Medida limpa do motor atual nas três camadas. | números registrados; nenhuma correção antes deles |
| **D1** | Analisador linear melhor (candidatos: perceptron com oráculo dinâmico e feixe, como Zhang e Nivre 2011; analisador por grafo com traços de segunda ordem, como MSTParser/TurboParser), escolhido por medida | LAS +5 pontos em pt e en no teste UD; ação e segurança não pioram |
| **D2** | Papéis semânticos: rotulador treinado no UP 2.0 + frames do PropBank/VerbNet ligados aos estados do builder no nível do frame. Substitui `STATE_OF_FRAME` e as listas de verbos. | F1 de argumentos registrado; ação melhora no dev |
| **D3** | Abdução com pesos aprendidos: modelo log-linear sobre os traços de custo, treinado no DocEdit (treino). As constantes inventadas são apagadas. | ação no teste DocEdit melhora; segurança: errados ≤ D0 |
| **D4** | Aprendizado contínuo: correções e definições ditas na conversa atualizam pesos e léxico sem mudar código. Curva de aprendizado medida num fluxo simulado de correções do treino DocEdit. | curva sobe; nada esquecido (regressão estável) |
| **D5** | Português na camada de ação: fontes humanas de pedidos em pt, com o mesmo oráculo | medida pt registrada e comparável à en |

Depois de D3, o motor antigo (`understand.py`) e as constantes substituídas são removidos.

## 6. Registro

### D0 (2026-10-01): medida limpa do motor atual, nos dev externos

Nenhuma correção antes destes números. Scripts em `experiments/externo/`; resultados em
`data/cache/externo_*_dev.json`.

**Estrutura** (`estrutura.py dev`)

| | UPOS | UAS | LAS |
|---|---|---|---|
| Bosque (pt) | 95,3 | 84,3 | 77,0 |
| PetroGold (pt) | 97,2 | 86,8 | 80,4 |
| Porttinari (pt) | 96,4 | 86,5 | 80,0 |
| EWT (en) | 93,7 | 80,8 | 74,0 |

| Universal Propositions (dev) | Predicados P / R / F1 | Argumentos (não rotulados) F1 | subj=A0, obj=A1 |
|---|---|---|---|
| Bosque (pt, prata), 7.494 frases | 66,3 / 42,0 / 51,5 | 79,0 | 77,5% |
| EWT (en, ouro), 2.002 frases | 65,3 / 36,4 / 46,8 | 75,8 | 72,5% |

A forma lógica só monta predicados da oração principal, coordenadas e completivas. Orações relativas, adverbiais e
nominais ficam de fora, e por isso a cobertura de predicados é de ~40%. Num texto, a maior parte do "quem fez o quê"
não é representada.

**Ação** (`acao.py dev`): DocEdit, 908 pedidos de outras pessoas, em inglês

| certo | ERRADO | perguntou | leitura certa (executando ou não) |
|---|---|---|---|
| 78 (8,6%) | 20 (2,2%) | 810 (89,2%) | 33,0% |

Decisões: não entendi 667, perguntar 78, executar 98, fato 61 (muitos pedidos estão no passado, "Moved X to the
left", e foram lidos como afirmação), 1 exceção.

Classes dos errados:
- origem lida como destino ("from right to mid" → `text-align: right`);
- metade de um pedido duplo executada ("Break the paragraph into 2. Moved the page number ...");
- palavras ancoradas em propriedades CSS por coincidência ("page", "cursor", "transform-origin", "bottom");
- "remove page no" → remover a página.

**Segurança** (`seguranca.py dev`): MASSIVE, 2.033 frases por língua, nenhuma sobre a página

| | errados | taxa | exceções |
|---|---|---|---|
| pt-PT | 14 | 0,69% | 6 (`IndexError`) |
| en-US | 18 | 0,89% | 3 (`IndexError`) |

Cerca de 13 dos 32 errados são "create a new list" e "add this item to the list". Num editor de página, criar uma
lista é uma leitura defensável. O oráculo estrito conta esses casos como erro, e a contagem fica assim registrada.
Os demais são substantivos ancorados a tipos de elemento por coincidência:
- "i need a manger" → div;
- "põe marco paulo" → progress;
- "no speaking please" → dialog;
- "tenho um voo" → nav.

**Leitura**
- O motor quase não entende pedidos reais: 8,6% de acerto contra 93,7% no M5 escrito por mim. Isso confirma o
  diagnóstico da §1.
- O erro silencioso é baixo (2,2% e 0,8%), mas não é zero.
- O maior bloco é "não entendi" (73%): é falta de cobertura, não erro de decisão.

### Projeto da D2 (escrito antes de codificar)

**Recursos**
- **Frames do PropBank 3.4** (`data/externo/propbank/`, 7.566 arquivos). Cada roleset traz:
  - seus papéis, com a **função** de cada um (PAG agente, PPT paciente, GOL destino, SRC origem, DIR direção, LOC
    lugar, VSP atributo, ...);
  - as ligações com classes do **VerbNet** e frames do **FrameNet**.
- **Universal Propositions**: frases anotadas com roleset e argumentos.
  - EWT, ouro: 12.543 frases de treino.
  - Bosque, prata: verbos portugueses anotados com rolesets ingleses ("encontrar" → `meet.03`). É daqui que sai o
    léxico verbo português → roleset, por contagem, sem tabela escrita à mão.

**Rotulador de papéis** (linear, no estilo do MATE/Björkelund et al. 2009)
1. **Identificação do predicado:** perceptron por palavra (lema, categoria, relação, categoria da cabeça).
2. **Roleset:** o mais frequente do lema no treino; se o lema não aparece, o de mesmo lema nos frames.
3. **Argumentos:** os candidatos são podados por Xue e Palmer (dependentes do predicado e dos seus ancestrais). Um
   perceptron escolhe o rótulo, ou NENHUM, usando:
   - o caminho de dependências;
   - a posição;
   - a voz;
   - o lema do predicado;
   - a palavra, a categoria e a relação do argumento;
   - a preposição.
4. O treino usa as árvores do próprio analisador (as que ele vai ver), não as árvores-ouro.

**Do roleset ao estado do builder**
- Os estados são ligados no nível do **frame do FrameNet**, uma vez, numa tabela pequena e documentada. Não é por
  verbo. Por exemplo:
  - Motion, Cause_motion, Placing → `moved`;
  - Removing, Destroying → `removed`;
  - Creating, Building, Intentionally_create → `added`;
  - Cause_change, Cause_change_of_position_on_a_scale → `style`;
  - Text_creation → `field:text`;
  - Name_conferral → `field:name`.
- Os papéis vêm pela **função**:
  - PPT é o elemento;
  - GOL é o destino ou o valor final;
  - SRC é a origem ou o valor anterior, que **nunca** é o valor pedido. Isso resolve na raiz a classe da D0 "from
    right to mid" → `right`.
- `STATE_OF_FRAME` e as listas de verbos do perfil são substituídos por isso.

**Portão da D2**
- F1 de argumentos rotulados no dev do UP, registrado.
- A ação no dev do DocEdit melhora.
- A segurança não piora.

### D1, primeira medida (2026-10-01): analisador rotulado, português, dev

`experiments/externo/d1_parser.py pt 10`: 20.081 frases de treino, 10 épocas, 24 min.

| dev | LAS atual | LAS D1 | ganho |
|---|---|---|---|
| Bosque | 76,95 | 81,45 | +4,5 |
| PetroGold | 80,38 | 85,35 | +5,0 |
| Porttinari | 79,95 | 85,08 | +5,1 |

O ganho sem nenhuma regra nova é de +4,5 a +5,1 LAS, e o UAS sobe de 2,6 a 3,1 pontos. O portão (+5 em todos)
ainda não está fechado: falta o Bosque, e o inglês não foi treinado.

### Revisão (2026-10-01), sem treinos novos

**Sondagem ilustrativa (não é medida):** 20 formas comuns de pedir em português, na página de `seguranca.py`.
- 1 executada certa ("tira essa imagem daí").
- 3 executadas **erradas**:
  - "joga o rodapé lá pra cima" → `transform-origin`;
  - "deixa a página mais moderna" → texto "mais moderna";
  - "o segundo botão tem que ser igual ao primeiro" → `align-items`.
- 2 perguntas corretas: "o título" é ambíguo, porque há dois.
- 14 não entendidas, entre elas:
  - "quero que o título fique em negrito";
  - "negrito no título, por favor";
  - "troca o texto do botão para Comprar";
  - "centraliza tudo";
  - "desfaz o que você fez".

**Causas, pela evidência da D0 e da sondagem**
1. **Execução sem confiança calibrada.** Palavras ancoradas por coincidência no grafo ("cima" → transform-origin,
   "igual" → align-items) passam pelos custos inventados. Falta uma probabilidade aprendida, com abstenção.
2. **Atos de fala indiretos.** Os casos não reconhecidos:
   - completiva no subjuntivo ("quero que ... fique");
   - pedido sem verbo ("negrito no título");
   - queixa como pedido ("o título tá muito pequeno" virou fato);
   - relato no passado.
3. **Cobertura lexical do português.** Paráfrases de edição ("engrossar a letra", "destacado", "some com") não
   chegam a estados.
4. **Estados que a representação não tem:**
   - desfazer;
   - escopo global ("tudo", "o site inteiro");
   - copiar o estilo de outro elemento ("igual ao primeiro");
   - mudança relativa sem valor ("um pouco maior").
5. **Metas vagas** ("mais moderna") precisam virar pergunta, nunca execução.
6. **O analisador novo da D1 ainda não está ligado ao motor.**

**Nova ordem**
1. Ligar a D1 ao motor.
2. Confiança aprendida com abstenção (parte da D3), treinada:
   - em DocEdit treino (positivos);
   - em MASSIVE treino (negativos).
3. Classificador aprendido do ato de fala.
4. D2 (papéis e frames).
5. Os estados que faltam, como tipos gerais de estado, nunca por frase.

## 7. Etapas em vigor (depois da auditoria)

| Etapa | Entrega | Portão |
|---|---|---|
| **A1** | **Espaço de ações e gerador de candidatas** (`nucleo/lang/acoes.py`), sobre a página e o catálogo do builder: estilo P=V, texto, nome, adicionar, remover, mover, comando, desfazer, copiar estilo; alvos em elementos e grupos. Sem modelo. | **cobertura**: a ação certa está entre as candidatas em ≥ 95% dos pedidos rotulados (M5, rodadas, congelados); número de candidatas por frase registrado |
| **A2** | **Dados de treino** (`experiments/externo/dados.py`): enunciados canônicos pt/en gerados das ações e expandidos por PPDB, OpenWordNet-PT e WordNet; DocEdit treino; MASSIVE treino como NENHUMA AÇÃO; as frases rotuladas que escrevi | contagens por fonte e por tipo de ação; nenhuma frase de dev ou teste nos dados |
| **A3** | **Ranqueador log-linear** p(ação \| frase, página) + NENHUMA AÇÃO + limiar calibrado no dev. O analisador da D1, os papéis e o grafo entram como traços. Os geradores de `interpret.py`, `base.COST`, `LIMIT` e `STATE_OF_FRAME` são removidos. | DocEdit dev: acerto muito acima de 8,6%; execução errada ≤ 0,5%; MASSIVE dev ≤ 0,5%; regressão: os conjuntos antigos sem errados |
| **A4** | **Aprendizado por interação:** cada escolha numa pergunta de esclarecimento e cada correção atualizam os pesos na hora (SHRDLURN) | curva de aprendizado num fluxo simulado (DocEdit treino); nada esquecido |

A D1 continua: ligar o analisador rotulado como fonte de traços, treinar o inglês e medir o teste UD no portão.
