# Plano D: compreensão aprendida e medida fora de mim

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
