# Especificação do usuário (governa o trabalho)

## Instrução definitiva posterior (2026-10-01, 18:05)

A missão e o modo de trabalho vigentes estão em `AGENTS.md` §0: entregar a web 8790 com compreensão PT/EN de
pedidos novos, execução calibrada com no máximo 0,5% de erros, pergunta com 2 ou 3 opções e aprendizado com
escolhas. A comprovação exige teste novo congelado antes de medir e medidas externas DocEdit dev/MASSIVE dev
PT/EN. O implementador escolhe abordagem e arquitetura e continua após portões reprovados; não espera revisor
ou permissão. Dados externos de treino e dados canônicos derivados do builder estão autorizados, separados dos
congelados. O DEV antigo não guia novos ajustes e o TEST A1 consumido não é repetido.

Esta direção substitui ordens anteriores de ritmo, sequência ou parada; mantém as proibições de LLM/neural,
conhecimento linguístico manual, remendos por frase e vazamento. Antes de cada commit são obrigatórios suíte
completa, auditoria, verificações de consumidores/congelados/determinismo/condições, diário no mesmo commit,
`scripts/verificar.py` e revisão do diff. A instrução posterior determina execução direta, sem subagentes,
pesquisa somente necessária e dados adicionais para o motor A1, sem classificador bag-of-words substituto. Triagem é barata; avaliações completas e ablações são separadas.
O restante abaixo preserva o registro histórico das especificações anteriores.

Este arquivo transcreve **na íntegra** as duas especificações que o usuário escreveu em 2026-10-01 na conversa
"Compreensão completa de linguagem". O texto entre as linhas é dele e não deve ser alterado. Em caso de conflito com
qualquer outro documento do repositório, **este arquivo vence**.

## Como ler a numeração (para não confundir)
- **A1 → A2 → A3 → A4** desta especificação são a sequência em vigor:
  - A1: listador e ranqueador de ações, com corpus TRAIN/DEV/TEST e relatório;
  - A2: parsing semântico completo;
  - A3: contexto e diálogo;
  - A4: execução e aprendizado integrado.
- As antigas "A1–A4" da §7 de `docs/plano_aprendizado.md` foram **substituídas** por estas.
- As etapas **E0–E6** e os objetivos **O1–O6** de `docs/roteiro_ccg.md` ficam como **referência técnica**: CCG,
  UBL/FUBL, aprendizado por execução e as metas externas (DocEdit, MASSIVE). Não são a sequência de trabalho.
- **GeoQuery e MATIS** são só evidência auxiliar de que o mecanismo funciona. Não voltam a ser objetivo.

## Direção posterior do usuário (2026-10-01, ~16:25): prevalece sobre a frase "NÃO reinicie a arquitetura"
Palavras do usuário, sobre como o implementador deve trabalhar:

> "O CERTO NÃO É VOCÊ DEIXAR ELE TRABALHAR LIVREMENTE, SEM FICAR DELIMITANDO ESCOPO? ELE NÃO DEVERIA FAZER AS
> COISAS, VER SE DA CERTO, MUDAR ABORDAGEM SE PRECISAR, DEFINIR OS MELHORES CAMINHOS,E TC?" e, em seguida,
> "ENTÃO FAÇA ISSO".

Como isso se aplica:
- o implementador escolhe técnicas, ordem e caminhos, e muda de abordagem, inclusive de arquitetura, quando a
  medida mostrar que o caminho atual não chega ao objetivo;
- o motivo de cada mudança de rumo vai no diário;
- o **objetivo** e as **proibições** das especificações abaixo continuam valendo integralmente: sem LLM, sem
  regex de intenção, sem `if/switch` por palavra, sem listas de paráfrases ou sinônimos, sem remendo por frase,
  sem gold no TEST e sem vazamento;
- a sequência A1 → A4 e os critérios de cada etapa servem como **marcos de medida**, não como roteiro obrigatório
  de implementação.

---

## Especificação 1 (2026-10-01, 13:59): arquitetura e A1

Pare de transformar GeoQuery/MATIS no objetivo do projeto. Eles são somente provas auxiliares. O objetivo real agora é fazer a aplicação compreender português e inglês livremente dentro do domínio do builder, inclusive formulações nunca vistas, sem catálogo manual de frases, regex de intenção, `if/switch` por palavra, sinônimos codificados à mão ou LLM.
Implemente a arquitetura completa de compreensão, começando pelo A1 e evoluindo até execução real.

1. ACTION GROUNDING AUTOMÁTICO
O universo semântico deve nascer da própria aplicação. Descubra automaticamente comandos, operações, entidades, propriedades, tipos, relações, restrições e efeitos já disponíveis no builder. Produza um `ActionSchema` tipado para cada operação. Não crie inventário linguístico comando por comando.
2. REPRESENTAÇÃO SEMÂNTICA INTERMEDIÁRIA
Crie uma IR independente de português/inglês capaz de representar:

* ação;
* entidade alvo;
* propriedades e valores;
* relações espaciais/estruturais;
* quantidade;
* comparação;
* negação;
* coordenação;
* sequência;
* modificadores;
* referências como “isso”, “ele”, “o anterior”;
* ações compostas.

Exemplo conceitual:
“deixe esse botão 20 pixels mais largo”
→ MODIFY(target=context.selected, property=width, operation=ADD, value=20px)
A frase não pode chamar diretamente um handler.

3. APRENDIZAGEM DO LÉXICO
Implemente indução palavra/morfema/frase → conceitos da IR usando evidência distribuída em muitos exemplos, seguindo aprendizagem cross-situational e léxico fatorado. Uma palavra não recebe significado porque alguém cadastrou uma regra; seu significado emerge da correlação entre linguagem, representação, contexto e execução.

Use como base técnica:

* Siskind — cross-situational lexical acquisition;
* Zettlemoyer & Collins — semantic parsing com CCG;
* Kwiatkowski et al. — factored lexicons / lexical generalization;
* Liang et al. — DCS e indução composicional;
* Artzi & Zettlemoyer — grounded semantic parsing para instruções→ações;
* Branavan et al. — aprendizagem de instruções por execução.

4. COMPOSIÇÃO
O sistema precisa aprender como significados menores formam significados maiores. Não quero classificação bag-of-words. “aumente a margem esquerda do segundo botão” deve ser derivado composicionalmente, distinguindo ação, propriedade, direção e referência ao objeto.
5. CONTEXTO E DIÁLOGO
Adicione estado discursivo para compreender continuações:
“selecione o painel”
“agora deixa ele menor”
“move um pouco para a esquerda”
“faz o mesmo com o outro”

A IR das frases posteriores deve resolver referências usando seleção, histórico semântico e estado atual da aplicação.

6. GERAÇÃO E RANQUEAMENTO
Para cada enunciado, gere semanticamente várias análises possíveis e pontue-as com parâmetros aprendidos. Depois faça grounding dessas análises contra os `ActionSchema` válidos no estado atual. Não escolha ações por regras textuais.
7. APRENDIZADO POR EXECUÇÃO
Use pares `(utterance, contexto, ação/estado final correto)` como supervisão. Quando somente o resultado final for conhecido, trate a derivação semântica como variável latente e aprenda quais interpretações produzem aquele resultado.
8. PORTUGUÊS E INGLÊS
Os dois idiomas devem convergir para a mesma IR. Teste explicitamente que paráfrases equivalentes nos dois idiomas produzem representações semanticamente equivalentes. O sistema deve generalizar morfologia, flexão e composição; não manter dois catálogos de comandos.
9. A1 — TESTE OBRIGATÓRIO AGORA
Construa primeiro o listador/rankeador de ações usando o catálogo extraído automaticamente do builder.

Monte um corpus do próprio aplicativo separado em TRAIN/DEV/TEST. O TEST não pode conter simples duplicações ou paráfrases usadas no treinamento.
Inclua:

* frases nunca vistas;
* sinônimos nunca associados diretamente à ação no teste;
* ordens diferentes das palavras;
* flexões;
* sujeito omitido;
* pronomes;
* elipse;
* negação;
* coordenação;
* comandos compostos;
* referências contextuais;
* português e inglês;
* erros leves de digitação;
* combinações novas de conceitos conhecidos.

Critério A1: a ação correta deve estar no Top-K das candidatas em ≥95% do conjunto TEST.
Além disso reporte Top-1, Top-3, Top-5 e resultados separados por categoria linguística.

10. TESTE DE INFERÊNCIA
Crie testes nos quais a formulação nunca apareceu no treinamento. Exemplo: se o sistema aprendeu separadamente os conceitos de aumentar, largura, painel e valor, deve interpretar uma combinação inédita desses conceitos sem exemplo específico daquela frase.
11. TESTE DE SIMULAÇÃO
Não valide somente IDs de ação. Execute a interpretação em uma cópia/sandbox do estado do builder e compare o estado resultante esperado com o produzido. Isso deve detectar interpretações semanticamente erradas que por acaso escolheram uma ação parecida.
12. TESTE DE CONTEXTO
Crie diálogos completos e verifique resolução de referência, continuidade, elipse e ações encadeadas.
13. ANÁLISE DE GENERALIZAÇÃO
Para cada erro, classifique a causa real: léxico, morfologia, composição, grounding, referência, ranking ou ausência de capacidade no ActionSchema. Corrija o mecanismo responsável; é proibido corrigir erro adicionando regra específica para aquela frase.
14. RESTRIÇÕES
São proibidos:

* regex para descobrir intenção;
* `if/switch` associando palavra/frase a ação;
* listas manuais de paráfrases;
* tabelas manuais de sinônimos usadas como motor semântico;
* templates do tipo “se disser X execute Y”;
* cadastrar todas as formas possíveis de pedir uma ação;
* LLM/API externa como mecanismo de compreensão.

Condicionais puramente algorítmicos internos são permitidos. O que é proibido é codificar conhecimento linguístico em condicionais.

15. ENTREGA
Não continue indefinidamente otimizando a replicação do GeoQuery. Registre o resultado já obtido como evidência técnica e volte ao builder.

Implemente A1 no projeto real, gere o corpus de avaliação, execute os testes e só considere A1 concluído quando houver relatório reproduzível demonstrando ≥95% de recall da ação correta entre as candidatas no TEST.
Depois avance para composição semântica, grounding, diálogo e execução, sempre usando o mesmo princípio: aprender generalizações, não acumular remendos.
O resultado final esperado não é um reconhecedor de comandos. É um semantic parser grounded que aprende uma linguagem de interação com o builder.

---

## Especificação 2 (2026-10-01, 14:25): correções obrigatórias antes de concluir a A1

Continue a implementação atual, mas corrija os pontos abaixo antes de considerar a etapa A1 concluída.
O trabalho agora está conceitualmente no caminho certo: IR independente de língua, grounding contra `ActionSchema`, execução em sandbox, corpus TRAIN/DEV/TEST e ranking de candidatas. NÃO reinicie a arquitetura e NÃO volte para GeoQuery como objetivo principal.
O objetivo continua sendo: compreender linguagem natural livre em português e inglês dentro do domínio do builder, inclusive formulações e combinações nunca vistas, sem LLM e sem conhecimento linguístico codificado em regex, `if/switch`, listas de comandos, tabelas manuais de paráfrases ou sinônimos usados como motor semântico.
CORREÇÕES OBRIGATÓRIAS

1. SEPARE RECALL DO GERADOR E QUALIDADE DO RANKER

A ação-ouro pode ser usada diretamente durante treinamento para calcular seus traços, mas isso NÃO pode contaminar a avaliação.
No DEV e principalmente no TEST:

* nunca injete a ação-ouro;
* nunca force a presença da ação correta;
* nunca use informação do gold para gerar candidatas;
* execute exatamente o mesmo pipeline que receberá uma frase real do usuário.

Meça separadamente:

* Candidate Recall@1
* Candidate Recall@3
* Candidate Recall@5
* Candidate Recall@10
* Ranking Top-1
* Ranking Top-3
* Ranking Top-5

O critério principal da A1 continua sendo:
`gold ∈ candidates` em pelo menos 95% do TEST no Top-K definido pelo plano.
Se o gold não foi gerado naturalmente, conte como falha mesmo que o ranker pudesse pontuá-lo corretamente.

2. NÃO ACEITE EXPLOSÃO COMBINATÓRIA COMO SOLUÇÃO FINAL

O gerador está produzindo aproximadamente 6.000 candidatas por frase. Isso pode servir temporariamente para diagnóstico, mas não é aceitável como arquitetura escalável.
Implemente busca hierárquica:
`utterance`
→ evidência semântica
→ recuperação de operações plausíveis
→ recuperação de alvos plausíveis
→ expansão somente dos slots compatíveis
→ composição estruturada
→ ranking final
Não monte o produto cartesiano completo entre operação × alvo × propriedade × valor × posição × tipo.
Use os tipos e restrições dos `ActionSchema` para eliminar combinações impossíveis ANTES da expansão.
Registre:

* número total de ações existentes;
* número médio de candidatas por frase;
* p50;
* p95;
* máximo;
* tempo médio de geração;
* tempo médio de ranking.

O sistema deve continuar funcionando quando o catálogo de ações crescer substancialmente.

3. NÃO TRANSFORME O CORPUS EM CATÁLOGO DE COMANDOS

TRAIN/DEV/TEST são instrumentos de aprendizado e avaliação, não um inventário de todas as formas possíveis de falar.
É proibido resolver cobertura aumentando indefinidamente listas do tipo:

* “deixe em negrito”;
* “coloque em negrito”;
* “faça ficar em negrito”;
* “torne negrito”;
* etc.

O aprendizado precisa decompor linguagem e reutilizar conhecimento.

4. ADICIONE TESTE FORTE DE GENERALIZAÇÃO COMPOSICIONAL

Crie splits específicos em que combinações inteiras sejam retiradas do TRAIN.
Exemplo:
TRAIN pode conter separadamente:

* aumentar largura de botão;
* diminuir altura de painel;
* alterar margem de cartão;
* selecionar painel;
* modificar botão.

Mas o TRAIN NÃO pode conter:
`aumentar largura de painel`
Então o TEST deve conter formulações inéditas como:

* “faz esse painel ficar mais largo”;
* “aumenta um pouco a largura dele”;
* “widen this panel a little”;
* “make the selected panel slightly wider”.

O sistema deve reconstruir o significado pela composição de conceitos aprendidos separadamente.
Crie testes equivalentes para:

* ação × entidade;
* propriedade × entidade;
* operação × propriedade;
* valor × propriedade;
* relação espacial × entidade;
* referência contextual × operação;
* ações compostas.

Reporte essas métricas separadamente como `compositional holdout`.

5. ADICIONE TESTE DE VOCABULÁRIO NÃO VISTO

Separe também casos em que palavras ou formas linguísticas do TEST não tenham ocorrido no TRAIN, mas possam ser relacionadas por recursos lexicais, morfologia, contexto ou grounding.
Meça pelo menos:

* lexical unseen;
* inflection unseen;
* paraphrase unseen;
* word-order unseen;
* compositional unseen.

Não altere o TRAIN depois de olhar individualmente para erros do TEST apenas para fazê-los passar.

6. GARANTA QUE OS PESOS INICIAIS NÃO ESCONDAM REGRAS MANUAIS

Audite todos os recursos usados pelo ranker.
É permitido usar evidência proveniente de:

* nomes e descrições do próprio builder;
* `ActionSchema`;
* documentação de propriedades;
* W3C;
* WordNet;
* Open Multilingual WordNet;
* Wiktionary;
* recursos morfológicos;
* corpus externo;
* coocorrência;
* dados de treinamento.

Não é permitido esconder regras específicas como:
`"negrito" => font-weight:bold`
com peso arbitrário escrito manualmente para fazer um caso passar.
Se existir qualquer mapeamento lexical direto, registre sua origem e diferencie:

* evidência externa;
* dado aprendido;
* heurística estrutural;
* regra manual proibida.

Produza auditoria automática procurando conhecimento de intenção hardcoded em Python/JSON/YAML/TS.

7. O GROUNDING DEVE SER TIPADO

Cada slot deve respeitar tipos e restrições do `ActionSchema`.
Exemplo:
`font-weight:bold`
não deve competir indistintamente com:
`width:20px`
ou:
`element.delete`
Use compatibilidade estrutural antes do ranking lexical.
A busca deve combinar:

* evidência linguística;
* tipo esperado;
* estado do documento;
* objeto selecionado;
* propriedades válidas;
* relações estruturais;
* histórico discursivo.

8. MANTENHA PROPERTY + VALUE COMO UNIDADE QUANDO NECESSÁRIO

A correção feita para casos como `font-weight:bold` está certa.
Generalize o mecanismo.
Alguns significados aparecem principalmente no par propriedade/valor e não isoladamente em um único slot.
Não crie tratamento específico para “negrito”.
O mecanismo deve funcionar igualmente para casos como:

* alinhamento central;
* display none;
* posição absoluta;
* overflow hidden;
* bordas;
* cores;
* unidades;
* estados booleanos;
* enumerações.

9. CONTEXTO NÃO PODE SER APENAS “ÚLTIMO ALVO”

Construa um estado discursivo explícito contendo pelo menos:

* entidade selecionada;
* entidades mencionadas recentemente;
* ação anterior;
* propriedade anterior;
* grupo/contêiner relevante;
* referências demonstrativas;
* referências ordinais;
* resultado da ação anterior.

Teste diálogos como:
“selecione o segundo cartão”
“deixa ele mais largo”
“agora aumenta o espaço interno”
“faz o mesmo no primeiro”
“desfaz isso”
A interpretação deve ser feita pela IR e pelo contexto, não por regras especiais para cada frase.

10. TESTE A IR DIRETAMENTE

Além da ação final, valide se frases semanticamente equivalentes produzem IR equivalente.
Exemplo:
PT:
“deixa esse painel vinte pixels mais largo”
EN:
“make this panel twenty pixels wider”
Devem convergir para algo semanticamente equivalente a:
`MODIFY(target=context.selected, property=width, operation=ADD, value=20px)`
A estrutura interna exata pode variar, mas o significado normalizado deve ser equivalente.

11. TESTE EXECUÇÃO REAL EM SANDBOX

Não valide somente IDs.
Para cada exemplo executável:

1. carregue o estado inicial;
2. interprete a linguagem;
3. gere a IR;
4. faça grounding;
5. execute;
6. compare o estado final produzido com o estado final esperado.

Reporte separadamente:

* semantic parse correct;
* action selection correct;
* execution result correct.

Uma ação parecida que produza estado errado é falha.

12. CRIE TESTES CONTRA “FALSOS ACERTOS”

Inclua pares de frases próximas lexicalmente mas semanticamente diferentes:

* aumentar largura / aumentar margem;
* mover elemento / aumentar margem esquerda;
* esconder / excluir;
* duplicar / copiar estilo;
* selecionar pai / mover para o pai;
* colocar abaixo / enviar para trás.

Isso deve provar que o ranker não está apenas escolhendo pela sobreposição de palavras.

13. TESTE PORTUGUÊS E INGLÊS COM A MESMA SEMÂNTICA

Os dois idiomas devem convergir para a mesma IR.
Reporte métricas independentes:

* PT;
* EN;
* cross-lingual equivalence.

Inclua também exemplos onde determinada construção foi observada principalmente em um idioma e a estrutura equivalente deve continuar sendo reconhecida no outro quando houver evidência suficiente.

14. PROÍBA CORREÇÕES CASO A CASO

Toda falha encontrada deve ser classificada em uma destas categorias:

* lexical induction;
* morphology;
* syntax/composition;
* candidate generation;
* grounding;
* property/value association;
* entity resolution;
* discourse/context;
* ranking;
* schema limitation;
* execution.

Corrija o componente responsável.
É proibido resolver um erro adicionando tratamento específico para a frase que falhou.

15. ADICIONE TESTE DE ABLATION

Execute pelo menos estas variantes:

* sem contexto;
* sem recursos lexicais externos;
* sem features estruturais;
* sem aprendizado;
* sistema completo.

Isso deve mostrar de onde vem o ganho de desempenho e revelar se o sistema depende excessivamente de alguma heurística escondida.

16. EVITE DATA LEAKAGE

Antes do TEST:

* congele TRAIN;
* congele DEV;
* congele TEST;
* gere hashes dos datasets;
* registre os hashes no relatório.

Cheque automaticamente:

* frases idênticas;
* frases normalizadas idênticas;
* simples remoção de acento;
* simples mudança de pontuação;
* simples reorder trivial;
* paráfrases artificialmente derivadas da mesma seed, quando identificáveis.

Não modifique exemplos individuais do TEST porque ficaram difíceis. Corrija o sistema.

17. AVALIAÇÃO OBRIGATÓRIA DA A1

Ao final, apresente uma tabela semelhante a:
Dataset:

* TRAIN: N
* DEV: N
* TEST: N

Candidate generation:

* Recall@1
* Recall@3
* Recall@5
* Recall@10
* candidates mean
* candidates p50
* candidates p95
* latency mean/p95

Ranking:

* Top-1
* Top-3
* Top-5

Generalização:

* lexical unseen
* inflection unseen
* word-order unseen
* compositional holdout
* context/reference
* negation
* coordination
* compound commands
* typos

Idiomas:

* PT
* EN

Execution:

* IR equivalence
* correct grounded action
* correct final sandbox state

Integrity:

* TRAIN/TEST exact overlap
* normalized overlap
* gold injection in TEST
* handwritten intent rules
* regex intent rules
* hardcoded paraphrase rules

18. CRITÉRIO PARA CONCLUIR A1

Não declare A1 concluída apenas porque o treino funciona.
A1 só passa se:

* a ação correta for recuperada naturalmente pelo gerador em ≥95% do TEST no Top-K definido;
* não houver gold injection no TEST;
* não houver regras linguísticas específicas escondidas;
* houver generalização composicional comprovada;
* PT e EN forem avaliados separadamente;
* o gerador permanecer computacionalmente viável;
* a avaliação for reproduzível;
* todos os números forem produzidos por execução real dos testes.

19. NÃO FIQUE PRESO INDEFINIDAMENTE NA A1

Se o mecanismo atingir os critérios, registre resultados e siga para:
A2 — semantic parsing completo;
A3 — contexto e diálogo;
A4 — execução e aprendizado integrado.
Não continue ajustando benchmarks externos depois que eles já tiverem cumprido sua função experimental.

20. RESULTADO FINAL ESPERADO

A arquitetura final deve ser:
`natural language`
→ análise lexical/morfológica aprendida
→ composição semântica
→ IR independente de língua
→ resolução de contexto
→ geração tipada de hipóteses
→ grounding contra capacidades reais do builder
→ ranking aprendido
→ execução
→ observação do resultado
→ nova evidência de aprendizado
O sistema NÃO deve ser um reconhecedor de frases ou comandos.
Ele deve ser um mecanismo de indução e composição semântica grounded no próprio builder.
Continue a implementação atual, aplique essas correções, execute os testes e apresente os resultados reais antes de declarar A1 concluída.
