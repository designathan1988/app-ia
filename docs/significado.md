# Significado: de palavras a entidades da máquina, em qualquer língua

## O problema de raiz

Hoje o significado está espalhado em mecanismos separados, cada um com suas regras:

- o léxico do catálogo;
- o léxico de valores CSS;
- os verbos de comando;
- os particípios;
- os quadros verbais com listas de verbos;
- o dicionário.

Cada frase nova cai num buraco entre eles, e cada buraco vira um remendo. Além disso, tudo isso está preso ao
português.

## A solução: um grafo de conceitos, uma busca de custo mínimo

### 1. Conceitos, não palavras

A unidade de significado é o **conceito**, com um identificador independente de língua: o ILI (Interlingual Index)
da Global WordNet, que é o mesmo nas WordNets de português, inglês, espanhol e outras.

### 2. As entidades da máquina também são conceitos

| Entidade | Exemplos |
|---|---|
| Ação | inserir, remover, mover, definir propriedade, executar comando X |
| Tipo de elemento | título, botão, seção |
| Propriedade | cor do texto, alinhamento |
| Valor | `right`, `bold`, `red` |
| Lugar | antes, depois, dentro |

Cada entidade é ligada a conceitos pelos próprios rótulos do builder (en e pt-BR), por:

- os lemas na WordNet de cada língua;
- as palavras-chave do W3C, que são palavras inglesas;
- as definições.

Nada é escrito à mão: a ligação sai dos rótulos.

### 3. Um único grafo

**Nós:**
- palavras de cada língua;
- conceitos (ILI);
- entidades da máquina.

**Arestas (com custo):**

| Aresta | Fonte | Custo |
|---|---|---|
| palavra → conceito | sentido na WordNet; ordem do sentido | menor no 1º sentido |
| conceito ↔ conceito | sinônimo (mesmo synset), hiperônimo, similar, derivação ("redondo" ↔ "arredondar"), antônimo marcado | por tipo de relação |
| palavra → palavra | definição do Wiktionary: palavras da definição; tradução pt ↔ en | maior |
| conceito/palavra → entidade | rótulos do builder (en, pt) e palavras-chave do W3C | 0 |
| aprendido | resposta do usuário, resultado mantido | 0, com proveniência; o desfazer aumenta o custo |

### 4. O significado de uma palavra

É o conjunto de entidades alcançáveis a partir dela, cada uma com o custo do **caminho mínimo** (Dijkstra com
limite). O caminho é a explicação. Exemplos:

- "pintar" → (def) "cor" → conceito *color* → família de propriedades de cor;
- "esconder" → (synset) "ocultar" → *hide* → comando `element.toggleHidden`;
- "rodapé" → *footer* → tipo `footer`;
- "escarlate" → (synset) *red* → valor `red`.

Um só mecanismo, para todas as classes de palavra e todas as línguas.

### 5. Composição

1. A frase é analisada em UD (Universal Dependencies). As relações (obj, obl, nmod, amod, case) são as mesmas em
   qualquer língua. O analisador muda por língua, não as regras.
2. Os papéis das ações são **tipados por entidade**:
   - definir-propriedade: elemento + propriedade + valor;
   - executar-comando: comando + elemento.
3. Cada argumento recebe as entidades alcançáveis das suas palavras, e cada papel aceita as do seu tipo.
4. A **abdução** escolhe o preenchimento de menor custo total: soma dos caminhos, mais as palavras não explicadas,
   mais as pressuposições (o definido pede um referente).
5. O valor é verificado contra o domínio da propriedade (gramática do W3C).
6. O verbo pode faltar ou ser desconhecido: a ação é inferida dos outros papéis. Por exemplo, "o título vermelho"
   tem elemento e valor de cor, logo a ação é definir a cor.

### 6. Decisão

- **Executar:** um preenchimento claramente mais barato que os outros, com caminhos curtos ou corroborados.
- **Confirmar:** o melhor depende de um caminho longo que nada na frase corrobora.
- **Perguntar:** há opções de custo próximo; elas ficam abertas para a resposta seguinte.

### 7. Diálogo e aprendizado

- Pergunta em aberto; respostas curtas (sim, não, ordinal, nome); elipse ("o mesmo no botão"); anáfora (último
  elemento tocado).
- Toda confirmação, resposta ou resultado mantido vira uma **aresta aprendida** no grafo, com proveniência. É
  aprendizado por indução de um exemplo, e generaliza porque a aresta liga a palavra ao conceito, não à frase.
- O desfazer encarece a aresta usada.

### 8. Outras línguas

Para o **inglês** bastam:
- a Open English WordNet (mesmos ILIs);
- um treebank UD inglês, para treinar o mesmo analisador linear;
- o dicionário inglês do Wiktionary (kaikki), para as definições.

As entidades já têm rótulos em inglês no catálogo do builder. Nenhuma regra muda.

## Ordem de implementação

| # | Etapa | Verificação |
|---|---|---|
| S1 | Grafo: carregar a OWN-PT (synsets, ILI, relações), a Open English WordNet (download) e o Wiktionary pt; ligar as entidades do builder | conferir a cobertura: quantas entidades têm conceito |
| S2 | Busca de custo mínimo palavra → entidades, com caminho | conjunto fixo de palavras → entidade esperada (a lista atual de casos como oráculo) |
| S3 | Trocar os mecanismos espalhados (léxico de valores, verbos de comando, particípios, ancoragem) pela busca no grafo | bateria do M5 sem regressão |
| S4 | Papéis tipados e ação inferida | conjunto rápido de frases livres no nível do entendimento (segundos) |
| S5 | Diálogo e aprendizado como arestas | testes de diálogo |
| S6 | Inglês: analisador UD inglês, Open English WordNet, mesmas frases traduzidas | mesmo conjunto rápido em inglês |

## Estado medido (`experiments/m5_livre.py`, nível do entendimento, segundos)

| Conjunto | Frases | Certo | Perguntou ou não entendeu | Errado |
|---|---|---|---|---|
| português, ajuste | 56 | 56 | 0 | 0 |
| português, validação (escrita antes das correções que a avaliam) | 36 | 26 → **35** | 1 | 0 |
| inglês, ajuste | 25 | 10 → **25** | 0 | 0 |
| inglês, validação (rodada uma vez antes das correções) | 20 | 13 → **18** | 2 | 0 |

**Honestidade:** os números depois da seta já viram as frases. Por isso a medida limpa é a primeira:
- português: 26 de 36;
- inglês: 13 de 20.

Bateria do M5, com o planejador e o juiz do builder: **top-1 92,4%, erro silencioso 0,0%**.

O analisador inglês (UD English-EWT, mesmo modelo linear) dá UPOS 93,7% e LAS 74,6%.

**O que ainda falta:**
- verbos compostos com nome ("left align");
- duplo objeto ("call the section Intro");
- causativos que a WordNet não liga ("sumir com" = remover).
