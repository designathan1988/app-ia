# Diário de progresso (preenchido pelo Codex)

Formato no `AGENTS.md` §7. A entrada mais nova fica no topo. Cada entrada tem o commit, o comando exato da medida e
os números.

---

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
