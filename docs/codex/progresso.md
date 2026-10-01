# Diário de progresso (preenchido pelo Codex)

Formato no `AGENTS.md` §7. A entrada mais nova fica no topo. Cada entrada tem o commit, o comando exato da medida e
os números.

Direção vigente: instrução definitiva do usuário de 2026-10-01, registrada em `AGENTS.md` §0. A missão continua
após a reprovação A1: dados novos, generalização lexical/composicional, medidas externas e web com execução
calibrada, opções e aprendizado. O TEST A1 está consumido e o DEV antigo não orienta novos ajustes. Portões
reprovados não são condição de parada; as restrições de integridade permanecem.

---

### 2026-10-01 18:15: resultado A1, missão definitiva e definição de pronto automatizada
- Verificação automática: `C:\ctv\n\Scripts\python.exe -m pytest -q tests --ignore=tests/test_web.py -o addopts= --junitxml=C:\Codex-Shared\nucleo\data\cache\verificar-20261001T213724Z-81120e05-pytest.xml` → 318 testes; 318 passaram, 0 falhas, 0 erros, 0 pulados. Comprovante: `C:/Codex-Shared/nucleo/data/cache/verificar-20261001T213724Z-81120e05.json`.
- Commit: este commit — Report failed A1 gate and enforce verified commits
- O que mudou: `docs/codex/relatorio_a1.md` registra o portão completo, categorias, idiomas, execução,
  ablações, custos e hashes. `AGENTS.md` §0 registra a missão definitiva e §9 os checks antes de cada commit.
  O topo da especificação preserva essa direção posterior. `scripts/verificar.py`
  valida fontes congeladas, diário, diferenças, suíte inteira e auditoria quando o motor muda; registra os
  números reais da suíte no diário e confere depois os arquivos/blobs exatos do índice. Nenhum código do motor
  foi alterado depois do portão.
- Motivo: o DEV chegou a 95,0% de cand@10, mas o TEST mostrou generalização insuficiente. A mudança de rumo
  será atacar dados e generalização lexical, sem remendo ou nova rodada do TEST e sem polir o DEV antigo.
  A instrução definitiva revogou a parada por reprovação e autorizou novos dados externos/canônicos separados.
  A definição de pronto evita publicação com verificação parcial ou diário separado.
- Medida: `(Get-Process -Id $PID).PriorityClass = 'BelowNormal'; $env:PYTHONIOENCODING = 'utf-8'; C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py | Tee-Object -FilePath data/cache/a1_portao.log`
  → execução única, 1.886 s, 6 épocas, 301 updates e 59 early updates; nenhum gold inválido.
  TEST n=189: cand@1/3/5/10 **46,6 / 58,2 / 63,0 / 67,2**; rank@1/3/5 **50,3 / 62,4 / 67,2**;
  IR/ação/estado **49,2 / 49,7 / 50,8**. DEV na mesma execução: cand@10 **95,0**, rank@1 e
  IR/ação/estado **81,7**. HOLDOUT n=51: cand@10 **76,5**, rank@1 **56,9**, IR/ação/estado **58,8**.
- Diagnóstico: 19 exemplos TEST sem ouro gerado, 43 com ouro gerado fora do Top-10; 96 falhas de IR,
  das quais 77 apesar da presença do ouro. Coordenação e comandos compostos: 16 exemplos, ouro gerado em
  todos, nenhum plano final correto. Vocabulário não visto (n=97): cand@10 47,4 e rank@1 35,1.
  Categorias responsáveis: candidate generation, ranking, lexical induction/morphology, syntax/composition,
  discourse/context; limitações de schema e associação de slots documentadas sem novo ajuste pelo TEST.
- Condições: latência sem perfilador medida separadamente no DEV aquecido (n=60), sem executar ações:
  média **93,856 ms**, p95 **201,641 ms**. Os tempos instrumentados não são usados como latência de produção.
  Auditoria final cobre conjuntos, diálogos e ablações: 5.384 chamadas completas, 271 funções;
  **0 regras de intenção, 0 regex de intenção, 0 pesos por palavra, 0 legado com efeito**.
- Verificação focada: `(Get-Process -Id $PID).PriorityClass = 'BelowNormal'; $env:PYTHONIOENCODING = 'utf-8'; C:/ctv/n/Scripts/python.exe -m pytest -q tests/test_verificar.py > data/cache/verificador_focados.log`
  → **47 testes passaram**. O verificador foi revisado por subagente; foram corrigidos filtros que podiam
  reduzir a suíte, modo do índice e aprovação de diário incompleto. O snapshot não cobre recursos externos;
  essa limitação está explícita. A aprovação final deste commit exige a execução completa do próprio verificador.
- Direção posterior do usuário: trabalho direto, sem subagentes e sem pesquisa longa. Um protótipo de
  recuperação de comandos por contagem foi retirado antes de ser ligado à web: ele não atende à composição
  exigida. A geração produziu 38.981 registros TRAIN (8.207 canônicos/variantes antes da divisão, 12.464 DocEdit
  train e 23.028 MASSIVE train no corpus total); o teste sintético de 371 itens não foi medido e não será usado
  como prova de linguagem natural. Preservar apenas a possibilidade de usar esses dados como treino adicional
  do A1, mantendo supervisão parcial do DocEdit e sem inventar ouro de alvo/propriedade.
- Falhas restantes: A1 reprovada (127/189 no Top-10; seriam necessários 180/189). Generalização lexical,
  composição e contexto insuficientes; web ainda no motor antigo. DocEdit/MASSIVE do motor novo não medidos.
- Próximo passo: comparar motores em desenvolvimento externo, incorporar dados não escritos à mão e estabelecer
  calibração e novo teste congelado; integrar o novo motor à web quando superar o antigo externamente.

### 2026-10-01 17:04: auditoria do portão e latência sem instrumentação
- Commit: `1a150a4` (push: ok)
- O que mudou: `auditoria.py --portao` encaminha para a única avaliação completa; o perfilador acompanha treino,
  conjuntos, diálogos e ablações dessa execução. O modo padrão continua só em TRAIN+DEV. A latência de inferência
  será medida separadamente no DEV aquecido, sem perfilador, sem execução e sem acessar gold; estatísticas são
  restauradas mesmo em caso de erro. Categoria: integridade da avaliação.
- Medida: `(Get-Process -Id $PID).PriorityClass = 'BelowNormal'; C:/ctv/n/Scripts/python.exe -m pytest -q tests/test_a1_latency.py tests/test_a1_audit_scope.py tests/test_a1_evaluation.py`
  → 10 testes passaram. Sem novo treino para essa mudança do avaliador. Último DEV real n=60: cand@10 95,0,
  rank@1 81,7, IR/ação/estado 81,7 / 81,7 / 81,7.
- Auditoria anterior preservada em `data/cache/a1_audit_isolated_pipeline_raw.json`: 227 enunciados, 284 funções;
  0 regex, 0 pesos por palavra, 0 legado com efeito; 1 coleção não revisada (`INIT`, pelo identificador de traço
  `lit`). Revisão da definição confirmou pesos por tipo de evidência, não por palavra. A classificação foi
  corrigida, mantendo o verificador independente `check_init`; seu teste detecta uma chave lexical artificial.
- Falhas restantes: as 11 falhas de IR do último DEV; nenhum resultado TEST disponível ainda.
- Próximo passo: executar o portão completo uma vez, com auditoria integrada e relatório real.

### 2026-10-01 17:02: ganho de consistência salvo e compatibilidade restaurada
- Commit: `408f676` (push: ok)
- O que mudou: geração e gold do treino agora recebem o mesmo traço genérico de ação. Pares propriedade/valor
  são recuperados uma vez por alvo dentro de cada busca, sem cache entre mudanças de pesos. O desempate está
  somente em `evidencia._from_graph`, preservando a API compartilhada do motor antigo; entidades legadas são
  filtradas antes do limite de recuperação. Categorias: ranking, candidate generation, integridade.
- Mudança de rumo: a suíte mostrou que ordenar o recurso compartilhado afetava o motor antigo. A ordenação foi
  transferida para o consumidor A1, sem remendo linguístico. A publicação reúne a consistência e essa correção
  de compatibilidade para não deixar um commit dependente da regressão do leitor compartilhado.
- Antes: `$env:PYTHONIOENCODING = 'utf-8'; C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev > data/cache/a1_dev_deterministic.log`
  → DEV n=60; cand@1/3/5/10 73,3 / 80,0 / 80,0 / 86,7; rank@1/3/5 75,0 / 81,7 / 81,7;
  IR/ação/estado 75,0 / 76,7 / 76,7; 173 updates.
- Depois: `$env:PYTHONIOENCODING = 'utf-8'; C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev > data/cache/a1_dev_isolated_pipeline.log`
  → DEV n=60; cand@1/3/5/10 **81,7 / 91,7 / 93,3 / 95,0**; rank@1/3/5 **81,7 / 91,7 / 93,3**;
  IR/ação/estado **81,7 / 81,7 / 81,7**; 301 updates, 59 early updates, 166/167 gold gerados na última época.
  Tempo até terminar o treino: 147 s; a medida anterior com consistência, sem cache, levou 325 s e teve as mesmas
  métricas agregadas (`a1_dev_consistency_deterministic.log`). Não se atribui toda variação de tempo somente ao cache.
- Verificação: `(Get-Process -Id $PID).PriorityClass = 'BelowNormal'; $env:PYTHONIOENCODING = 'utf-8'; C:/ctv/n/Scripts/python.exe -m pytest -q tests --ignore=tests/test_web.py > data/cache/a1_tests_isolated_pipeline.log`
  → **267 testes passaram**. A rodada anterior teve 259 passes e 1 falha em
  `test_understand::test_place_says_the_side`; os 3 casos desse teste passaram após restaurar o leitor compartilhado.
- Auditoria: `$env:PYTHONIOENCODING = 'utf-8'; C:/ctv/n/Scripts/python.exe experiments/a1/auditoria.py > data/cache/a1_audit_isolated_pipeline.log`
  → 227 enunciados; resultado e revisão do único alerta de classificação descritos na entrada acima.
- Falhas restantes: 11 de IR (resolução de entidade, associação propriedade/valor, composição, contexto,
  polaridade e inserção). DEV atinge a meta de trabalho; isso não demonstra o resultado do TEST.
- Próximo passo: parar os ajustes no DEV e medir o portão da A1, preservando todos os conjuntos congelados.

### 2026-10-01 16:23: reprodutibilidade e ordenação da evidência
- Commit: `68bd7c6` (push: ok)
- O que mudou: empates de `concepts.meanings` têm desempate canônico antes do corte Top-40; keywords, cores,
  evidências e tipos de slot são percorridos em ordem estável. Categoria: candidate generation/integridade.
  O teste sintético provou que inverter âncoras empatadas mudava as entidades recuperadas antes da correção.
- Medidas do código-base, com sementes diferentes, sem fixar uma semente como solução:
  - `$env:PYTHONIOENCODING = 'utf-8'; $env:PYTHONHASHSEED = '1'; C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev > data/cache/a1_dev_repro_before_1.log`
  - `$env:PYTHONIOENCODING = 'utf-8'; $env:PYTHONHASHSEED = '2'; C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev > data/cache/a1_dev_repro_before_2.log`
  - Ambas: 173 updates, 67 early updates; DEV n=60, cand@1/3/5/10 73,3 / 80,0 / 81,7 / **86,7**;
    rank@1/3/5 75,0 / 81,7 / 81,7; IR/ação/estado 75,0 / 76,7 / 76,7.
- Medida depois: `$env:PYTHONIOENCODING = 'utf-8'; C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev > data/cache/a1_dev_deterministic.log`
  → 173 updates, 67 early updates; DEV n=60, cand@1/3/5/10 73,3 / 80,0 / 80,0 / **86,7**;
  rank@1/3/5 75,0 / 81,7 / 81,7; IR/ação/estado 75,0 / 76,7 / 76,7. Cand@5 caiu uma frase; demais medidas principais iguais.
- Testes: `(Get-Process -Id $PID).PriorityClass = 'BelowNormal'; C:/ctv/n/Scripts/python.exe -m pytest -q tests/test_a1_determinism.py > data/cache/a1_determinism_after.log`
  → 3 passaram; os treinos de 16 itens TRAIN, 2 épocas, têm estatísticas, pesos exatos e índice iguais nas sementes
  1/2 e após preflight TRAIN+DEV. O teste de soma já passava antes; a soma não foi modificada.
- Limite da conclusão: não foi demonstrada a causa exata dos 180 updates históricos. O preflight TRAIN+DEV não
  alterou o treino curto; nenhum gold reservado foi executado para investigar a hipótese do revisor.
- Publicação imediata determinada pela Revisão 3: o commit ocorreu com os testes focados passando, sem esperar
  o DEV em curso. Auditoria dinâmica e suíte completa ficaram para a validação seguinte, sem alegar que já passaram.
- Experimentos não publicados: referências v1 (`a1_dev_references.log`) cand@10 85,0, rank@1/IR/ação/estado 71,7;
  v2 (`a1_dev_references_v2.log`) cand@10 88,3, rank@1/IR/ação/estado 68,3. Foram retirados por regressão.
- Falhas restantes: referências, polaridade, propriedade/valor, repetição e inserção; TEST ainda intocado.
- Próximo passo: publicar a consistência treino/inferência após a única nova medida DEV; iniciar então o prazo
  de 2 horas de desenvolvimento, com portão obrigatório ao final (Revisão 3).

### 2026-10-01 15:57: comunicação obrigatória entre sessões
- Commit: `450eb29` (push: ok)
- O que mudou: seção 8 do `AGENTS.md`, com as sete regras de comunicação solicitadas pelo usuário.
  Mudança documental; nenhum mecanismo semântico ou conjunto foi alterado.
- Medida: `git diff --check -- AGENTS.md` → 0 erros. Sem nova avaliação para uma mudança documental;
  última medida real: DEV n=60, cand@10 86,7; rank@1 75,0; IR/ação/estado 75,0 / 76,7 / 76,7
  (`C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev > data/cache/a1_dev_before.log`).
- Falhas restantes: as mesmas da medida inicial; correção de referências ainda em avaliação.
- Próximo passo: concluir a medida de referências e informar a comparação antes de publicar o mecanismo.

### 2026-10-01 15:55: isolamento do desenvolvimento e medida inicial limpa
- Commit: `b378dee` (push: ok)
- O que mudou: `avaliar.py --dev` valida gold somente de TRAIN/DEV e não inspeciona combinações HOLDOUT;
  `auditoria.py` percorre somente TRAIN+DEV. Antes, ambos alcançavam conjuntos reservados ao portão.
  Corrigida a chamada Win32 de prioridade (o handle era truncado: erro 6); execução agora falha explicitamente
  se não conseguir baixar a prioridade. Acrescentados artefatos locais e diagnóstico reproduzível do DEV.
  Categoria: integridade da avaliação, pré-requisito dos cinco mecanismos. Nenhum conjunto foi alterado.
- Medida: `C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev > data/cache/a1_dev_before.log`
  → DEV n=60; cand@1/3/5/10 = 73,3 / 80,0 / 81,7 / **86,7**;
  rank@1/3/5 = 75,0 / 81,7 / 81,7; IR/ação/estado = 75,0 / 76,7 / 76,7; 15 falhas de IR.
  Treino: 167 itens, 173 updates, 67 early updates, 189 s até terminar o treino; gold inválido TRAIN/DEV: 0.
  Comparação com a passagem: cand@10 permaneceu 86,7; rank@1 e IR caíram de 76,7 para 75,0.
  A diferença não foi descartada nem atribuída a uma causa sem investigação.
- Verificação: `(Get-Process -Id $PID).PriorityClass = 'BelowNormal'; C:/ctv/n/Scripts/python.exe -m pytest -q tests --ignore=tests/test_web.py > data/cache/a1_tests_harness.log`
  → 255 testes passaram, código de saída 0. Os dois testes do avaliador também passaram no teste focado posterior.
- Falhas restantes: os cinco mecanismos da passagem e uma falha adicional de polaridade no DEV.
  TEST não avaliado nesta sessão; leitura dos conjuntos selados restrita aos hashes.
- Próximo passo: medir a correção dos traços de ordinais e cadeias de genitivo.

### 2026-10-01 15:40: passagem do Claude para o Codex
- Commit: `1960f1c` (push: ok)
- O que mudou: nada no motor. Esta entrada registra o ponto de partida (`estado.md`).
- Medida: `C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev` → DEV n=60:
  - cand@1/3/5/10 = 75,0 / 81,7 / 81,7 / 86,7; cand@todas 91,7;
  - rank@1 = 76,7;
  - IR / ação / estado = 76,7.
- Falhas restantes: 14. Cinco mecanismos (`estado.md`):
  - ordinais e genitivo;
  - polaridade relativa;
  - propriedade+valor;
  - "o mesmo";
  - inserção com posição.
- Próximo passo: fechar a A1 no DEV, um mecanismo por commit.
