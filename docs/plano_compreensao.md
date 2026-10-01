# Compreensão: diagnóstico e plano (reconstrução do motor)

## 1. Diagnóstico do motor atual (medido, não opinado)

**Arquivo e estrutura**
- `nucleo/lang/understand.py`: 2.357 linhas e 79 funções. Destas, **14 são geradores de leitura escritos à mão**:
  - estilo por valor, família de propriedade, medida, lado, comparativo, retirada de valor;
  - valor-objeto, nomeação, comandos, verbo-valor, dicionário, verbo leve, construções;
  - o núcleo dos quadros.
- O histórico mostra 50 commits nesta fase.
- A cada rodada de frases novas, a medida limpa (antes de corrigir) não converge:

  | Rodada | Medida limpa | Errados |
  |---|---|---|
  | 3 | 17/30 | 1 |
  | 4 | 22/30 | 3 |
  | 5 | 17/30 | 1 |
  | 6 | 22/30 | 1 |

**Como a frase é tratada hoje**
1. O analisador sintático (UD) produz a árvore de dependências completa: quem modifica quem, sujeito, objeto,
   complemento, cópula, coordenação.
2. **A árvore é descartada.** `_pieces` achata a frase numa sequência de pedaços cortados nas preposições.
3. Os 14 geradores procuram, cada um, um padrão linear sobre esses pedaços:
   - "objeto + valor";
   - "valor + lugar";
   - "família + dono + valor";
   - …
4. A abdução escolhe entre as leituras que os padrões produziram.

**Causa-raiz**
- **Não há composição de significado.** O sentido não é construído a partir da estrutura da frase. Ele é
  reconhecido por padrões, um padrão por construção.
- Como a língua combina estruturas livremente, o número de padrões necessários é ilimitado, e cada frase nova pode
  cair fora deles.
- Remendos aumentam a lista, mas não mudam a natureza. Por isso:
  - a medida limpa não sobe de forma estável;
  - surgem regressões, como "fundo" virar lugar ou um patch que desligou a cópula;
  - erros silenciosos aparecem a cada rodada.

**O que está certo e fica**
- **Ancoragem palavra → conceito → entidade da máquina** (grafo de conceitos com ILI, WordNets, dicionário): é
  independente de língua e mede bem.
- **Abdução por custo** (Hobbs): escolher a interpretação mais barata que explica a frase.
- **As restrições-objetivo** (estados do documento) e o planejador que as alcança.
- **Diálogo, aprendizado e verificação.**

## 2. Pesquisa: como sistemas sem LLM compõem significado a partir de UD

**UDepLambda** (Reddy et al., EMNLP 2017)
- Converte árvores UD em formas lógicas por um conjunto pequeno de regras **por relação de dependência**, e não por
  construção.
- Funciona quase independente de língua (inglês, alemão, espanhol).
- Superou as linhas de base em perguntas sobre bases de conhecimento.
- Lição: a composição é feita por relação UD (nsubj, obj, obl, xcomp, amod, nmod, conj…), que são
  universais. [arxiv 1702.03196](https://arxiv.org/abs/1702.03196v3) · [ACL D17-1009](https://aclanthology.org/D17-1009/)

**PredPatt / Universal Decompositional Semantics** (White et al., 2016)
- Extrai estrutura predicado-argumento de árvores UD com padrões **não lexicalizados e independentes de língua**.
- Precisão de 86% em inglês sobre árvores-ouro.
- Lição: as regras gerais sobre a árvore cobrem as construções de uma vez. A qualidade depende da árvore, e
  é preciso robustez a erros de análise. [docs](https://decomp.readthedocs.io/en/latest/package/decomp.semantics.predpatt.html)

**Predicação secundária e resultativos**
- "Deixe o título vermelho", "make the image 400px wide", "o título tem que ficar vermelho" são uma só coisa: um
  evento cujo resultado é um estado do objeto.
- Em UD isso aparece como xcomp, cópula ou adjetivo predicativo, ligado à árvore. Tratado como estado-resultado, um
  único mecanismo cobre o que hoje são 5 geradores. [UD xcomp](https://universaldependencies.org/la/dep/xcomp.html)

**Bases teóricas que já estavam no plano**
- semântica de eventos neo-davidsoniana (papéis como relações);
- DRT para referentes e discurso;
- interpretação como abdução (Hobbs 1993);
- gramática de construções: a construção contribui significado, aqui dado pelos papéis da árvore.

## 3. A nova arquitetura

```
texto ─► frases ─► árvore UD (+ alternativas de ligação) ─► FORMA LÓGICA (composição por relação UD)
                                                              │  eventos, entidades, estados, modalidade,
                                                              │  quantificação, coordenação, perguntas
                                                              ▼
                           ANCORAGEM de cada nó (grafo de conceitos → tipo, propriedade, valor, comando, lugar)
                                                              ▼
                           INFERÊNCIA DO ESTADO-RESULTADO (abdução): que estado do documento torna verdadeira
                           a forma lógica? (existe / não existe / está em / tem propriedade=valor / campo / flag)
                                                              ▼
                           DECISÃO (executar / confirmar / perguntar) → planejador → diálogo e aprendizado
```

### 3.1 Forma lógica (nova, independente de língua)

**Composição.** A árvore UD vira um grafo de significado com estes elementos:
- **Evento:** o predicado e seus papéis.
- **Papéis, por relação UD**, numa tabela única e universal:
  - nsubj → agente ou tema;
  - obj → tema;
  - iobj → destinatário;
  - obl → papel dado pela preposição (lugar, destino, origem, valor, instrumento);
  - xcomp, ou adjetivo predicativo → **resultado**;
  - advmod de direção → destino.
- **Preposições:** em cada língua, só se diz qual papel cada uma marca. É gramática fechada; o resto é universal.

**Entidades** (cada sintagma nominal vira uma descrição):
- núcleo;
- determinante (definido, indefinido, quantificador, ordinal, demonstrativo, possessivo);
- modificadores (amod, nmod, compound, acl, relativas);
- nome próprio ou literal.

**Estados**
- cópula ("o título tem que ser vermelho");
- predicativo ("quero o título sublinhado");
- resultativo ("deixe o título vermelho", "make it 400px wide").

**Ato de fala e modalidade**
- ordem, pedido polido, desejo, obrigação, pergunta (com a variável perguntada), afirmação.

**Coordenação.** "e" e "and" distribuem: "deixe o título vermelho e o botão azul" são dois estados.

**Textos.** Um texto se divide em frases, e os referentes do discurso (DRT) atravessam as frases: "ele", "isso", "o
mesmo".

### 3.2 Ancoragem
Mantém-se a ancoragem atual (grafo de conceitos + dicionário + catálogo do builder), aplicada a **cada nó da forma
lógica** em vez de pedaços de frase:
- o núcleo de uma entidade → tipo de elemento ou nome;
- um adjetivo ou nome de valor → (propriedade, valor);
- uma palavra de dimensão → propriedade;
- uma preposição → papel.

### 3.3 Inferência do estado-resultado (substitui os 14 geradores)

**A pergunta da abdução.** Qual estado do documento, entre os tipos que a máquina sabe alcançar, torna verdadeira
a forma lógica com o menor custo? Tipos de estado:
- existe elemento T em L;
- não existe E;
- E está em L;
- E tem P = V;
- E tem campo F = V;
- E tem flag X.

**Evidências e custos**
- O verbo é **evidência** (o seu conceito dá uma probabilidade a priori sobre os tipos de estado, vinda das
  âncoras), não porteiro. Um verbo desconhecido não impede o entendimento, se os argumentos determinam o estado.
- Os argumentos impõem tipos: o valor tem de caber na propriedade (gramática do W3C); a propriedade tem de se
  aplicar ao elemento; o lugar é um elemento.
- Quantificação e ordinais escolhem os elementos; o definido pressupõe referente; a novidade exige criação.
- Cada palavra não explicada custa; uma palavra com significado ignorada impede a execução.

Uma só inferência cobre:
- "bota negrito no parágrafo", "deixe o parágrafo em negrito", "o parágrafo tem que ficar em negrito";
- "quero o parágrafo em negrito", "make the paragraph bold", "the paragraph should be bold".

Isso acontece porque todas têm a **mesma forma lógica**: estado(parágrafo, negrito).

### 3.4 Robustez a erros de análise
O analisador linear erra cerca de 20% das ligações (LAS de 80 no português, 75 no inglês). Quando a forma lógica
não fecha (um papel sem tipo compatível), gera-se alternativas de religação local:
- um sintagma preposicional ligado ao verbo ou ao nome;
- um adjetivo como modificador ou como predicativo;
- uma palavra etiquetada como verbo ou como nome.

A abdução escolhe entre elas. Isso substitui os consertos atuais de etiquetagem ("to" como verbo, "left" como
"leave").

### 3.5 Informação, não só pedidos
Uma afirmação ("o site é de uma cafeteria", "o botão principal é o Assinar") vira fato no núcleo de conhecimento
(Datalog, M1), com fonte e data, e fica disponível para perguntas e referências.

## 4. Protocolo de avaliação (fixado antes de codificar)

1. **Conjuntos atuais como regressão:** ajuste, validação pt e en, rodadas 3 a 6 (cerca de 230 frases), mais a
   bateria do M5 (670 pedidos) e os testes.
2. **Um conjunto novo de validação**, escrito antes da reconstrução e congelado por hash: 120 frases em pt e en,
   incluindo parágrafos com vários pedidos e afirmações. Só é medido nos portões, nunca olhado durante o trabalho.
3. **Métricas:** certo, perguntou ou não entendeu, **errado** (meta: 0). Também a cobertura da forma lógica (frases
   cuja forma lógica fecha sem nó solto).
4. **Portão de troca:** o motor novo substitui o antigo só quando, nos conjuntos atuais, tiver acerto maior ou
   igual e zero erro, e no congelado for melhor que o antigo.

## 5. Etapas

| Etapa | Entrega | Portão |
|---|---|---|
| C0 | Conjunto congelado (120 frases, pt e en, frases, parágrafos e afirmações); medida do motor atual nele | hash registrado |
| C1 | **Forma lógica** a partir da árvore UD: tabela universal de relações → papéis; entidades com determinantes, quantificadores e ordinais; estados (cópula, predicativo, resultativo); ato de fala; coordenação | testes de forma em pt e en |
| C2 | Ancoragem por nó da forma lógica (reuso do grafo) | cobertura da ancoragem |
| C3 | Inferência do estado-resultado por abdução tipada → restrições | conjuntos atuais ≥ antigo, errado = 0 |
| C4 | Religação local para erros de análise | cobertura da forma lógica ↑ |
| C5 | Textos: frases, coordenação, discurso entre frases; perguntas sobre a forma lógica; afirmações como fatos | parágrafos do congelado |
| C6 | Troca: o motor novo assume, os 14 geradores e `_pieces` são removidos | portão da §4 |

## 5a. Registro de C1 (feito) e projeto de C2–C3

### C1: resultado medido
- **X3** (`experiments/x3_kbest.py`): o feixe sobre as transições do analisador guloso **piora** a análise.

  | Medida | UAS em inglês |
  |---|---|
  | Guloso | 83% |
  | Feixe | 76% |
  | Oráculo das 4 melhores | 82,5% |

  O k-best ingênuo foi descartado.
- **Robustez por edições locais** (`nucleo/lang/alternatives.py`): sobre a análise gulosa, gera alternativas por
  dois tipos de edição, e o custo de cada alternativa é o número de edições.
  - **Reetiquetar** uma palavra entre as categorias que os léxicos (MorphoBr, WordNets) lhe dão. Uma palavra
    desconhecida é de classe aberta.
  - **Religar** um ou dois dependentes na fronteira de ligação, mantendo a árvore projetiva; o rotulador dá a nova
    relação.
- **Regras UD na forma lógica** (`logic_form.py`):
  - o sujeito controlado passa para o xcomp;
  - o modal governa só um complemento verbal;
  - um adjetivo ou particípio sob um verbo é resultado;
  - um obj com preposição é obl, e um nominal sem preposição é obj.
- **Testes:** `tests/test_logic_form.py` (estruturas em pt e en dentro de 2 edições).

### C2: ancoragem por nó (`nucleo/lang/ground.py`)
Cada nó da forma lógica recebe denotações tipadas com custo. O vocabulário vem de `grounding.meanings`, do léxico do
catálogo e do índice de valores do W3C, nunca de listas no código.

**Menção**
- `Ref`: nós da página.
  - Vem do tipo, do nome, do pronome (seleção ou discurso), do ordinal ou do universal.
  - As frases ligadas restringem por contenção: "do cartão", "in the header".
- `Kind`: um tipo a criar. Vem de um indefinido ou de algo dito novo.
- `Prop`: uma propriedade ou um campo, com dono opcional dado pela frase "de/of" ligada. Rótulos de várias palavras
  ("cor de fundo", "font size") casam sobre o núcleo, os modificadores e as frases ligadas.
- `Val`: uma lista de (propriedade, valor). Vem de um valor nomeado ("negrito", "azul"), de um literal ("24px",
  "#fff", texto entre aspas) ou de uma medida ("320px de largura": literal + propriedade).
- `Place`: uma relação de lugar (dentro, antes, depois, início, fim) com âncora. A locução vem do perfil de língua
  (`locais`): caso + núcleo + "de".

**Predicado**
- Evidência sobre os tipos de estado:
  - pelo quadro: existir, remover, mover, estilo, texto, nome;
  - pelo comando do builder;
  - pelo par verbo → valor ("centralizar");
  - pelos significados do grafo.
- Um verbo de ligação ou cópula não dá preferência e deixa o estado ser decidido pelos argumentos.
- Um verbo desconhecido dá evidência uniforme com custo; os argumentos podem decidir, e a decisão então é
  confirmar.

### C3: inferência do estado-resultado (`nucleo/lang/interpret.py`)
Para cada análise alternativa e cada predicado, preenche os tipos de estado por **papéis tipados**:
- `style(E, P, V)`: V pode vir de result, attr, um obl de valor ou o próprio obj; P de uma `Prop` ou do valor; E do
  dono, do tema ou de um obl de lugar. Exige que V caiba em P (gramática W3C).
- `command(E, C)`, `added(T, lugar)`, `removed(E)`, `moved(E, lugar)`, `field(E, texto|nome, literal)`.

**Custo**
- custo da análise + custo das denotações + desacordo com a evidência do verbo;
- \+ cada nó com significado que fica sem uso (impede a execução);
- \+ suposições de referente.

**Decisão**
- A menor leitura sem rival próximo de efeito diferente → executar.
- Um rival próximo de efeito diferente → perguntar, com as alternativas.
- Um verbo desconhecido com argumentos que decidem → confirmar.
- Uma afirmação → fato, nunca execução.

A saída são as mesmas restrições-objetivo do planejador atual, então a troca (C6) não muda o resto do sistema.

### Registro de C2–C5 (feito em 2026-10-01)
Ferramenta: `experiments/m5_livre.py --novo`, que roda os mesmos conjuntos com o motor novo
(`nucleo/lang/interpret.py`).

**Primeira medida limpa do motor novo**
- Conjuntos: ajuste 45/56, validação 25/36, inglês 15/25, inglês validação 14/20.
- Rodadas 3–6: 15, 16, 15, 15 de 30.
- Erros: 5, 1, 2, 1 e 3, 2, 4, 7.

**Mecanismos acrescentados, todos gerais (nenhum por frase)**
- **Ancoragem e referência**
  - pressuposição do definido (o tipo que a página tem);
  - tipo só pelo núcleo da menção;
  - dono por frase "de/of" ou por composto nominal ("the paragraph font");
  - totalidade ("inteiro", "whole");
  - pronome como conteúdo.
- **Propriedades e valores**
  - contenção de rótulo ("fonte" + 32px → tamanho da fonte);
  - família pelo núcleo do rótulo ("margem");
  - lado pelo perfil ("em cima" → superior);
  - só propriedades que o builder tem;
  - comparativos relativos ao valor atual, perguntando o número quando não há valor;
  - retirada de valor;
  - coordenação de valores;
  - literal com forma CSS = valor;
  - frase como texto, mais cara se tem palavras com significado, salvo quando o campo dito é texto.
- **Verbo como evidência**
  - quadros;
  - comandos (sem contar duas vezes os comandos dos quadros);
  - particípio que nomeia o valor (centralizado, underlined), por sinônimo quando o verbo não tem quadro;
  - comando inteiro pelo significado ("descer" = mover para baixo);
  - verbos com partícula do grafo ("jogar fora", "get rid of");
  - infinitivo regular de forma desconhecida;
  - propriedades que o verbo nomeia ("alinhar").
- **Construções (Goldberg)**
  - movimento causado e inserção com custo próprio;
  - causativo ("faz o parágrafo sumir");
  - nominalização ("faz uma cópia de");
  - particípio de comando como resultado ("deixa escondidas");
  - dativo ("give X a white background").
- **Forma lógica**
  - controle de sujeito e de objeto;
  - modal governa complemento verbal; adjetivo modal ("seria possível");
  - afirmação só com sujeito antes do verbo e sem auxiliar prospectivo;
  - parataxe;
  - preposição composta (`fixed`);
  - aposto com preposição é modificador.
- **Análise**
  - palavras funcionais mantêm a categoria;
  - palavra de lugar pode ser preposição;
  - religação não projetiva como passo intermediário;
  - possessivo inglês separado como na EWT.
- **Discurso (C5)**
  - frases pela pontuação;
  - orações pela vírgula como segmentação alternativa;
  - cortesia;
  - elemento saliente e propriedade em tópico entre orações;
  - elemento criado como marcador.

**Portão de regressão (§4.4) atingido**: 0 erros, e maior ou igual ao motor antigo em todos os conjuntos.

| Conjunto | Novo | Antigo |
|---|---|---|
| Ajuste | 56 | 56 |
| Validação pt | 35 | 35 |
| Inglês | 25 | 25 |
| Inglês validação | 20 | 20 |
| Rodada 3 | 28 | 27 |
| Rodada 4 | 29 | 29 |
| Rodada 5 | 30 | 27 |
| Rodada 6 | 29 | 27 |
| **Total** | **252** | **246** |

Os rótulos das rodadas 3–6 foram escritos para o motor antigo, que foi ajustado nelas; para o novo, cada rodada
foi medida limpa antes das correções. Duas expectativas foram corrigidas, porque o significado é inequívoco:
"negrito e itálico" quer os dois estilos, não uma pergunta.

### Portões medidos em 2026-10-01
- **Regressão:** passou. Novo 252 contra antigo 246; ≥ em todos os conjuntos; 0 errados.
- **Bateria M5** (669 pedidos sobre cenários do builder, julgados pelo `matchDocument` do próprio builder):
  passou.

  | Motor | Acerto | Erro silencioso | Tempo |
  |---|---|---|---|
  | Antigo | 92,4% | 0 | 65 s |
  | Novo | 92,5% | 0 | 406 s |

  O novo partiu de 62,9% e 27 erros silenciosos. As classes corrigidas foram:
  - camada (estado e breakpoint);
  - rótulo mais longo e rótulo exato;
  - extras do elemento criado;
  - interlocutor;
  - decimais na divisão de frases;
  - literais de função CSS;
  - propriedades W3C alcançáveis (não abreviações de longhands do builder);
  - atributos pelo manifesto;
  - palavras-chave W3C como valor;
  - nomes de elementos são referências.
- **Conjunto congelado** (88 itens, medido uma vez): **NÃO passou.**

  | Motor | Certo | Perguntou | Errado |
  |---|---|---|---|
  | Antigo | 58 | 28 | 2 |
  | Novo | 63 | 20 | **5** |

  A primeira tentativa quebrou: o elemento criado numa frase não passava para a seguinte (marcador `$novo`). Só
  essa quebra estrutural foi corrigida antes da medida. Nenhum ajuste foi feito pelos itens do conjunto.
- **Consequência:** a troca (C6) não acontece; o motor antigo continua em uso.
- **Próximo passo:**
  1. Rodada 7 de desenvolvimento, nova e escrita antes de qualquer correção, com o tipo de material do congelado:
     parágrafos, discurso, afirmações, inglês e pedidos ambíguos que devem ser perguntados.
  2. Medição limpa e correção por classe.
  3. Novo conjunto congelado (v2, com hash novo) para o próximo portão. O v1 já foi visto em parte.

### Rodada 7, congelado v2 e troca (C6)
- **Rodada 7** (`experiments/rodada7.py`, escrita antes de medir):

  | Medida | Novo | Antigo |
  |---|---|---|
  | Limpa | 40/13/3 | 32/19/5 |
  | Depois das correções por classe | 53/3/0 | — |

  As classes corrigidas foram:
  - nomes de várias palavras e entre línguas (conceitos compartilhados dos WordNets);
  - identidade na restrição;
  - cortesia como leitura;
  - elipse do verbo (gapping);
  - detecção de língua que ignora nomes;
  - sujeito sem preposição;
  - palavra de classe aberta etiquetada como preposição;
  - literais de função CSS.
- **Congelado v2** (`experiments/congelado2.py`, 71 itens numa página nova, hash `1bf134f9…` registrado antes de
  rodar), medido uma vez:

  | Motor | Certo | Perguntou | Errado |
  |---|---|---|---|
  | Antigo | 52 | 16 | 3 |
  | Novo | **60** | **8** | 3 |

  O novo é melhor que o antigo, com o mesmo número de erros.
- **Portão §4.4 atingido:**
  - conjuntos atuais ≥ e 0 errados (252 contra 244, depois da correção de duas expectativas de coordenação);
  - bateria M5: 92,8% contra 92,4%, 0 erros silenciosos;
  - congelado v2 melhor.
- **C6 feito:** a sessão e o assistente usam `interpret.understand_request`.
  - As definições ensinadas e os verbos aprendidos são tratados antes do motor.
  - O texto inteiro vai ao motor, que separa frases e orações.
  - Execução em etapas atômicas, com o id real do elemento criado substituindo o marcador `$novoN`.
  - "fato" e "cortesia" são respondidos sem mudança.
  - A elipse ("o mesmo no …") é tentada antes do motor.
  - Um elemento com o nome padrão do seu tipo é nomeado pela palavra do tipo.
  - Um valor nomeado só pelo verbo, numa propriedade improvável para o elemento, é confirmado antes.
- **Falta (honesto):**
  - os 3 erros do congelado v2, acima da meta de 0 (§4.3), que serão atacados com uma rodada nova, não pelo v2;
  - o código antigo (14 geradores, `_pieces`) ainda existe, e o motor novo ainda usa ajudantes dele (`_prior`,
    `_placement`, `paraphrase`);
  - o motor novo é cerca de 7 vezes mais lento que o antigo (0,7 s contra 0,1 s por pedido na bateria).

### Depois de C6 (2026-10-01)
- **Rodada 8** (`experiments/rodada8.py`, uma terceira página, focada no que não deve ser feito):

  | Medida | Novo | Antigo |
  |---|---|---|
  | Limpa | 27/9/7 | 20/17/6 |
  | Depois das correções por classe | 37/6/0 | — |

  As classes corrigidas foram:
  - negação é proibição;
  - pergunta com palavra interrogativa não é pedido;
  - verbo leve não gera texto;
  - quantidades;
  - modelo de conteúdo do builder;
  - coordenação distribuída;
  - nomes entre línguas respeitam o tipo presente;
  - o contexto nunca substitui um elemento dito;
  - o atributo da cópula não inclui a oração;
  - nome padrão só entre pares de nome padrão.
- **Perguntas** refeitas sobre a forma lógica e a ancoragem nova.
- **Ensino por definição** refeito sobre a forma lógica (`teaching.py`). O verbo de definição é classe fechada do
  perfil, e as expressões regulares com palavras do português foram retiradas.
- **Separação:** o que a aplicação usa está em `nucleo/lang/base.py` (34 definições).
  - `understand.py`, o motor antigo, só é carregado pelos experimentos, como linha de base.
  - A aplicação não o carrega mais.
- **Ponte com o builder:** o impasse do `stderr` não lido foi corrigido, e a ponte é encerrada na saída.
- **Velocidade:** cerca de 0,14 s por pedido (eram 1,1 s).
- **Bateria M5:** 93,1%, 0 erros silenciosos (o antigo, 92,4%).

### Verificação de ponta a ponta e rodada 9 (2026-10-01)
- **Interface web** (pré-visualização "nucleo", porta 8790), uma conversa real em pt e en. Achou classes que os
  conjuntos não cobriam, todas corrigidas pela raiz:
  - um rótulo de estado de uma palavra usado na sua função gramatical não é estado ("Depois deixa…" virava `::after`);
  - um pronome pessoal não explica palavras penduradas nele ("deixa ele azul e centralizado" perdia o azul);
  - um literal classificado pelo rótulo antes dele é o valor desse campo ("the text 'X'");
  - **resultados que dependiam da ordem dos pedidos**: o índice de valores, os nomes de cores e as âncoras dos
    comandos eram guardados em cache na língua do primeiro pedido; agora são construídos sempre a partir dos dados
    portugueses;
  - perguntas:
    - palavras interrogativas são variáveis, não anáforas;
    - um rótulo exato de tipo não recebe propriedade do grafo ("título" ≠ right);
    - a propriedade perguntada é escolhida pela probabilidade a priori e pelo que o elemento tem definido;
    - perguntas de sim/não são verificadas pela leitura do próprio motor contra o documento;
    - a página é consultada antes do código, e o índice do código (cerca de 20 s) só é montado quando a pergunta não
      é sobre a página.
- **Rodada 9** (`experiments/rodada9.py`): uma quarta página, com estilos e textos definidos. Tem 44 pedidos (pt/en,
  textos com discurso) e 24 perguntas.

  | Medida | Pedidos (certos/perguntou/ERRADO) | Perguntas |
  |---|---|---|
  | Limpa | 36/4/4 | 23/1/0 |
  | Depois das correções | 41/3/0 | 24/0/0 |

  As classes corrigidas foram:
  - advérbio antes do verbo é de discurso ("Primeiro…", "Agora…", "Then…");
  - comando alcançado longe no grafo não impede cortesia ("Obrigado!");
  - nomes de vários termos da página são uma unidade lexical ("the Massas frescas heading");
  - compostos nominais do inglês restringem por contenção ("the card title");
  - nome cujo elemento contradiz o tipo dito cede ao nome entre línguas desse tipo ("the menu section" = «Cardápio»);
  - o estado **selecionado**: o comando `selection.select` do builder, que torna o elemento saliente;
  - "o texto do X" exige uma propriedade de texto.
- **Ambiguidade texto/caixa num controle de formulário.**
  - Os conjuntos antigos esperavam "o botão azul" = cor do texto; a rodada 9 esperava o fundo.
  - O builder define os controles de formulário (`applies.ts`: input, textarea, select, button, progress, meter),
    que são desenhados como caixa preenchida. Neles, a cor nua é igualmente o texto ou o fundo.
  - Leituras empatadas (diferença < 0,25) de um mesmo predicado, quando dão o mesmo valor ao mesmo elemento em
    propriedades do texto e da caixa, agora são rivais, e o motor **pergunta**.
  - Uma pergunta sobre uma frase de um texto leva o texto inteiro em cada opção: a resposta executa tudo.
  - Por isso o conjunto de regressão foi de 252 para 245 certos: os 7 restantes perguntam, e há 0 errados.
- **Medidas:** rodada 7 52/4/0; rodada 8 38/5/0; M5 93,1% e 0 silenciosos.

### Congelado v3 (2026-10-01), medido uma vez
- `experiments/congelado3.py` (hash b7ff1caf6532): uma página nova (academia), 57 pedidos e 20 perguntas.
- **Pedidos 39/12/6, perguntas 19/1/0. O portão falhou** (a meta é 0 errados). O conjunto está gasto e não será
  usado para ajuste.
- As classes visíveis (gerais) vão para uma rodada 10 nova, com outras frases:
  - detecção da língua contaminada pelos nomes da página;
  - cor de duas palavras ("cinza claro");
  - nome com número ("Depoimento 1");
  - "chama ela de X" depois de criar;
  - coordenação "e depois" com verbo de remoção;
  - referência pelo plural do nome ("o título dos planos");
  - "padding" de todos os lados.

### Rodada 10 (2026-10-01): as classes do congelado v3, em outras frases
- `experiments/rodada10.py`: uma quinta página (livraria), com 37 pedidos e 9 perguntas.

  | Medida | Pedidos | Perguntas |
  |---|---|---|
  | Limpa | 17/14/6 | 6/3/0 |
  | Depois das correções | 35/2/0 | 9/0/0 |

- As classes corrigidas, todas gerais:
  - a língua é detectada sem os nomes da página nem o que está entre aspas;
  - cores de duas palavras ("azul claro", "dark green"):
    - a cor nomeada do CSS que o tom forma;
    - o tom em inglês vem dos conceitos compartilhados das wordnets;
    - entre vários tons, vence o prefixo que forma mais nomes de cor do CSS;
  - nome com número ("Livro 3");
  - pronome depois do verbo de um pedido é objeto ("chama ele de X");
  - o verbo de um quadro e um nome dito são palavras com significado (deixá-los de fora custa);
  - verbo com conjunção própria é oração coordenada ("e depois apaga");
  - oração coordenada a um pedido não é cortesia;
  - um shorthand sem lado vale para todos os lados, como define o W3C ("12px of padding");
  - um lado dito em qualquer parte da oração escolhe a propriedade do lado;
  - classe de elementos pela palavra comum dos nomes ("o segundo livro", "how many books");
  - um ordinal ou "todos" fala de um conjunto, não de um nome;
  - plural não é nome próprio;
  - um composto nominal restringe por contenção;
  - quando a contenção rejeita o nome, valem os elementos do tipo dito ali dentro;
  - os sentidos de substantivo vêm primeiro na comparação entre línguas (5 sentidos);
  - **valor atual pela folha de estilo base do builder** (`src/core/render/base.ts`): um comparativo sem valor
    definido escala a partir do que a página mostra (h2 = 1,5rem = 24px; o corpo tem 16px; propriedades herdadas
    seguem o W3C);
  - num controle de formulário, "maior" sem a propriedade é perguntado;
  - a mesma propriedade definida duas vezes num texto: vale a última ("maior, tipo 22px");
  - leitura de afirmação empatada com uma de pedido: confirma;
  - a pergunta de uma parte de uma coordenação leva o pedido inteiro em cada opção.
- **Expectativas corrigidas nos conjuntos de desenvolvimento** (registravam limitações, não o significado):
  - "cinza claro" agora espera lightgray;
  - "16px de padding" agora espera os quatro lados (`m5_livre` passou a aceitar uma lista de mudanças esperadas);
  - o teste "comparativo sem valor pergunta" agora espera o valor da folha base.
- **Medidas:** regressão 245 com 0 errados; rodada 7 52/4/0; rodada 8 39/4/0; rodada 9 41/3/0 e 24/24;
  **M5 93,7%** (era 93,1%) com 0 silenciosos.

### Congelado v4 (2026-10-01), medido uma vez
- `experiments/congelado4.py` (hash e2efc6312ee7): uma página nova (clínica veterinária), 59 pedidos e 16 perguntas.
- **Pedidos 53/5/1, perguntas 16/16.** O v3 tinha dado 39/12/6.
- O portão ainda falha por um errado: "make the copyright gray and italic" executou só o itálico.
- O conjunto está gasto. As classes visíveis vão para a rodada 11, com outras frases:
  - coordenação de dois valores em inglês perdendo o primeiro;
  - lado com "embaixo de";
  - nome antes do tipo com palavras funcionais ("the O que fazemos heading");
  - "remove the italics";
  - "the X button text to 'Y'" lido como afirmação;
  - "the X image 200px wide".

### Rodada 11 (2026-10-01): as classes do congelado v4, em outras frases
- `experiments/rodada11.py`: uma sexta página (padaria), com 33 pedidos e 8 perguntas.
- **Limpa: 23/7/3 e 7/1/0. Depois: 33/0/0 e 8/8.**
- Classes corrigidas, todas gerais:
  - **análise do inglês:**
    - os modelos ingleses nunca viram o marcador "VALOR" e o encadeavam num nome próprio; em inglês, um literal
      aparece aos modelos como uma palavra do seu tipo que o treebank inglês conhece (número, cor, nome próprio
      frequente do próprio dicionário do etiquetador), e o nome da página como esse nome próprio;
  - **reanálise estrutural nova:** um objeto cuja última palavra o analisador fez núcleo (ou que ficou pendurada
    depois do núcleo) é reanalisado como objeto + predicado secundário ("make the X section background yellow",
    "make the X image 500px wide"), e o mesmo na oração copular ("is the note italic?"). Custa uma edição e nunca
    usa como predicado uma palavra que é rótulo de campo, propriedade ou tipo;
  - uma segunda raiz é sempre erro e pode ser religada sob a primeira;
  - adjetivos coordenados são valores coordenados ("red and bold");
  - tirar um valor volta ao valor inicial da propriedade (W3C: "none" no sublinhado);
  - o dono de um campo inclui os nomes antes do rótulo ("the Fazer pedido button text");
  - uma propriedade de outro lado contradiz o lado dito ("margem embaixo" não é margin-top);
  - o nome do elemento como núcleo dispensa a checagem de tipo ("a nota" = «Nota»);
  - o núcleo definido que é rótulo de campo não é valor ("the card text" não é background-clip: text).
- **Medidas:** regressão 245 com 0 errados; rodadas 7 a 11 com 0 errados (52/4, 41/2, 41/3, 35/2, 33/0); M5
  93,7% e 0 silenciosos.

## 6. Limites honestos
- A forma lógica é tão boa quanto a árvore; a religação local reduz, mas não elimina, os erros de análise.
- O vocabulário vem do grafo e do dicionário. Palavras e sentidos que nenhuma fonte liga ao que a máquina faz
  continuam desconhecidos, mas passam a ser **perguntados e aprendidos** na conversa, não remendados no código.
- "Entender qualquer texto" sobre qualquer assunto exige conhecimento de mundo fora do domínio do builder. O motor
  entende a estrutura de qualquer frase; o significado acionável é o que se ancora no que a máquina sabe fazer, e
  o resto vira fato registrado ou pergunta.
