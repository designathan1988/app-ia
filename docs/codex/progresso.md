# Diário de progresso (preenchido pelo Codex)

Formato no `AGENTS.md` §7. A entrada mais nova fica no topo. Cada entrada tem o commit, o comando exato da medida e
os números.

Direção vigente (2026-10-01, Revisão 4 e decisão direta do usuário): o implementador escolhe técnicas e ordem,
inclusive mudanças de arquitetura justificadas por medidas. Estão revogados o prazo de 2 horas, as ordens de
método e o critério de aceite das revisões anteriores. Permanecem todas as restrições de integridade.
Mudança de rumo: priorizar defeitos de aprendizagem demonstrados por testes, começando pela consistência dos
traços; as tentativas de referências não serão reaplicadas automaticamente. A evidência medida decidirá.

---

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
