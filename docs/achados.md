# Achados

Defeitos e comportamentos relevantes descobertos durante o desenvolvimento, com a evidência de cada um.

| Id | Onde | Achado | Evidência | Estado |
|---|---|---|---|---|
| M1-1 | núcleo (motor) | As premissas da justificativa eram gravadas na ordem de avaliação semi-ingênua, não na ordem do corpo da regra. A prova não correspondia à regra. | Pego pelo **checador independente** no diferencial (seed com recursão) | corrigido em `engine.py` |
| F0-1 | builder-6 | `text.set` sobre um elemento cujo conteúdo não é texto (ex.: "HTML incorporado") **lança exceção** em vez de recusar. A interface nunca chama isso, mas o contrato "operação inválida previsível é recusada" não vale. | `tests/test_builder_bridge.py` (sequência aleatória, seed 1, passo 41) | o planejador usa o tipo de conteúdo do manifesto como pré-condição; o defeito do builder foi registrado |
| F0-2 | builder-6 | Nomes de camada com acento (pt-BR) viram classes CSS quebradas na exportação: `Seção` → `se-o`, `Título` → `se-o__t-tulo`. | Exportação via ponte sem interface | tarefa separada sugerida ao usuário |
