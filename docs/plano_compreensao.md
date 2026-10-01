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

## 6. Limites honestos
- A forma lógica é tão boa quanto a árvore; a religação local reduz, mas não elimina, os erros de análise.
- O vocabulário vem do grafo e do dicionário. Palavras e sentidos que nenhuma fonte liga ao que a máquina faz
  continuam desconhecidos, mas passam a ser **perguntados e aprendidos** na conversa, não remendados no código.
- "Entender qualquer texto" sobre qualquer assunto exige conhecimento de mundo fora do domínio do builder. O motor
  entende a estrutura de qualquer frase; o significado acionável é o que se ancora no que a máquina sabe fazer, e
  o resto vira fato registrado ou pergunta.
