# Achados

Defeitos e comportamentos relevantes descobertos durante o desenvolvimento, com a evidência de cada um.

| Id | Onde | Achado | Evidência | Estado |
|---|---|---|---|---|
| M1-1 | núcleo (motor) | As premissas da justificativa eram gravadas na ordem de avaliação semi-ingênua, não na ordem do corpo da regra. A prova não correspondia à regra. | Pego pelo **checador independente** no diferencial (seed com recursão) | corrigido em `engine.py` |
| F0-1 | builder-6 | `text.set` sobre um elemento cujo conteúdo não é texto (ex.: "HTML incorporado") **lança exceção** em vez de recusar. A interface nunca chama isso, mas o contrato "operação inválida previsível é recusada" não vale. | `tests/test_builder_bridge.py` (sequência aleatória, seed 1, passo 41) | o planejador usa o tipo de conteúdo do manifesto como pré-condição; o defeito do builder foi registrado |
| F0-2 | builder-6 | Nomes de camada com acento (pt-BR) viram classes CSS quebradas na exportação: `Seção` → `se-o`, `Título` → `se-o__t-tulo`. | Exportação via ponte sem interface | tarefa separada sugerida ao usuário |
| X1-1 | GF (gf-rgl, português) | O paradigma automático de flexão erra: `mkA "inferior"` gera o feminino "inferiora"; `mkV "aplicar"` conjuga "apficar / apfico / apfiquei". | `cc -table` no GF; `experiments/x1_gf.py` | contornado: todas as formas vêm do MorphoBr (tabelas explícitas) |
| X1-2 | GF (românicas) | `MkVPI` e `ConjVPI` (coordenação de infinitivos) declarados, mas `variants {}` em `ExtendRomanceFunctor.gf`: "mostrar ou ocultar" não analisa. | leitura do código + falhas no X1b | a implementar por nós |
| X1-3 | medição (nosso) | Sem proteções, o medidor do X1b contava mensagens de erro como análises e reportou 100% com uma gramática que nem compilava. | comparação com o modo base | corrigido: só árvores contam, frase-controle, abortar em erro de compilação |
| X1-4 | GF `Extend` | `CompoundN` recursivo sem poda: ~9 milhões de análises para um rótulo, mais de 21 GB de RAM. | X1c | compostos pelo léxico; teto de resultados e pesos; limite de memória nos experimentos |
