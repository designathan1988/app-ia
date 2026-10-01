# Auditoria: por que o motor não entende linguagem natural (2026-10-01)

Feita sobre o código, as medidas externas da D0 e o rastreamento passo a passo de frases que falham
(`árvore → forma lógica → ancoragem → leituras → decisão`). Nenhum treino novo.

## 1. O fato central

**A etapa que liga frase a ação não aprende de nenhum dado.**
- O único aprendizado do pipeline está na etiquetagem e na análise sintática.
- Da forma lógica até a decisão, tudo é escrito à mão:
  - `interpret.py`: 61 funções, 15 constantes de custo e 30 testes `if ... in (...)`;
  - `ground.py`: 46 funções e 13 constantes;
  - `base.COST`: 16 custos;
  - limiar fixo `LIMIT = 4.0`.
- Nenhum par (frase, ação) jamais foi usado para ajustar nada.
- Cada forma nova de pedir só passa a funcionar se eu escrever código para ela. Foi isso que gerou 27 commits de
  rodadas e congelados.

Os 14 geradores do motor antigo não desapareceram: renasceram sobre a forma lógica como `_style`, `_commands`,
`_structural`, `_fields`, `_value_removal`, `_selected`... A troca C0–C6 mudou a entrada dos geradores (árvore em
vez de pedaços), não a natureza deles.

## 2. Como as frases morrem (rastreamento real)

| Frase | Onde quebrou | Causa de arquitetura |
|---|---|---|
| "quero que o título fique em negrito" | o analisador pôs "fique" como `advcl`; `logic_form.build` só sobe de "querer" por `xcomp/ccomp/obj/csubj` | composição por nome exato de relação: um rótulo errado e o predicado some (0 leituras) |
| "troca o texto do botão para Comprar" | "troca" etiquetado NOUN; uma análise alternativa achou a leitura certa (texto = "Comprar"), mas custou 5,0 > `LIMIT` 4,0 | custo inventado com limiar fixo descarta a leitura certa; a ambiguidade (há dois botões) vira "não entendi" em vez de pergunta |
| "negrito no título, por favor" | predicado sem verbo: o gerador de estilo só procura o valor num argumento | cada construção exige um gerador |
| "centraliza tudo" | o verbo foi entendido (`text-align: center`), mas "tudo" não denota nada | quantificador universal sem denotação: 0 leituras |
| "some com a imagem" | lema escolhido "somar" (homógrafo de "sumir"); "sumir com" não existe no léxico | uma decisão dura no lema: o resto não tem como recuperar |
| "joga o rodapé lá pra cima" | "cima" casou com a palavra-chave CSS `top`, e a leitura `transform-origin: top` custou 2,0: **executou errado** | coincidência lexical barata vence; a leitura certa (mover o rodapé para o alto) nem é gerada, porque o verbo "jogar" não dá `moved` |
| "make the first heading bold" | árvore errada ("bold" como objeto), mas uma alternativa salvou | funciona por sorte das alternativas, não por modelo |

**Padrão:** é uma cadeia de decisões duras em série (etiqueta → árvore → composição por relação → lema → ancoragem
→ gerador → custo → limiar). Cada elo erra uma fração, e qualquer erro mata a frase. E nada nessa cadeia aprende com
o erro.

## 3. Por que nunca fechou, nem em português nem em inglês

1. **Gerar significado por regra exige cobrir todas as construções.** A língua tem cauda longa, então a lista não
   termina. Medido: as rodadas frescas, antes das correções, ficaram entre 46% e 82% sem tendência.
2. **Os custos à mão não sabem o que é provável.** "cima" → `transform-origin` custa 2,0 e "texto = Comprar"
   custa 5,0. Só dados dizem que a segunda é mais provável.
3. **Falhar é o padrão.** Quando nenhum gerador produz leitura, o resultado é "não entendi". Isso aconteceu em 73%
   dos pedidos reais.
4. **A medida era minha.** Até a D0, eu escrevia as frases de teste. Os 93,7% do M5 escondiam os 8,6% reais.
5. **O Plano D atacou só parte disso.** O analisador melhorou (+4,5 a +5,1 LAS), mas a D2 e a D3 ainda se
   penduravam nos geradores de `interpret.py`. Um analisador melhor só alimenta melhor um gerador que continua
   rígido.

Entender português e inglês sem modelo de linguagem não é fácil. A estagnação, porém, não vem da dificuldade da
língua: vem desta escolha de arquitetura, que é minha.

## 4. A solução: gerar todas as ações possíveis e ranquear com um modelo aprendido

É a abordagem que funciona sem LLM na literatura de interpretação semântica ligada a um mundo:
- SEMPRE, analisador flutuante: Berant et al. 2013; Pasupat & Liang 2015;
- Overnight: Wang, Berant & Liang 2015;
- SHRDLURN, aprendizado por interação: Wang, Liang & Manning 2016;
- naturalização de linguagem: Wang et al. 2017.

**1. O espaço de ações da página é finito e enumerável.** Ele é feito de:
- elemento, ou grupo de elementos ("tudo", "todos os títulos");
- tipo de ação: estilo P=V, texto, nome, adicionar T em L, remover, mover para L, comando, desfazer, copiar estilo;
- argumentos: valores vindos da gramática do W3C e dos literais da frase.

Gera-se tudo o que tem alguma ligação lexical com a frase. **Nunca há zero leituras**, e a leitura certa está
sempre entre as candidatas.

**2. Um ranqueador log-linear aprendido**, p(ação | frase, página), mais a classe **NENHUMA AÇÃO**. Os traços
ligam palavras a partes da ação:
- (palavra, propriedade), (palavra, valor), (lema, tipo de ação);
- caminho de dependência do verbo até a palavra que nomeia o elemento;
- preposição × papel ("from" → origem, nunca o valor);
- função PropBank do argumento;
- nome, texto, tipo e ordinal casados com o elemento;
- tempo e modo verbal, pessoa, pergunta.

Analisador, papéis e grafo de conceitos viram **traços com peso**, não portões. Um erro de árvore pesa, mas não mata
a frase.

**3. Dados de treino, nenhum escrito pelo usuário:**
- **Enunciados canônicos gerados do próprio espaço de ações** (Overnight), em pt e en, expandidos por paráfrases:
  - PPDB, que tem inglês e português;
  - sinônimos do OpenWordNet-PT e do WordNet.

  O rótulo é mecânico, porque cada frase nasce da ação. O gerador só cria dados de treino: ele nunca roda na
  aplicação.
- **DocEdit treino** (12.464 pedidos humanos): supervisão fraca do tipo de ação e do componente.
- **MASSIVE treino** (11.514 por língua): exemplos de NENHUMA AÇÃO.
- **As frases que já escrevi** (M5, rodadas, congelados; ~1.000 pedidos rotulados): viram **treino**, não medida.
- **Interação:** cada escolha do usuário numa pergunta de esclarecimento é um exemplo rotulado (SHRDLURN). É aqui
  que "qualquer forma de pedir" converge com o uso.

**4. A decisão é calibrada.**
- Executar só quando p ≥ θ.
- θ é escolhido no dev para ter ≤ 0,5% de execução errada.
- Abaixo de θ, perguntar mostrando as 2 ou 3 ações mais prováveis. A resposta vira dado de treino.
- Metas vagas ("mais moderna") ficam naturalmente abaixo de θ e viram pergunta.

**5. O que sai:**
- os geradores de `interpret.py`;
- `base.COST`, `LIMIT` e as constantes;
- `STATE_OF_FRAME`;
- a composição por nome de relação como portão.

Fica a forma lógica como fonte de traços. Ficam o planejador, o diálogo e o ensino.

**6. Medida:** a mesma da D0, externa e limpa. DocEdit dev/teste, MASSIVE dev/teste e UD/UP. As frases de treino
nunca entram nela.
