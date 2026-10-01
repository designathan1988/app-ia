# Diário de progresso (preenchido pelo Codex)

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

Formato no `AGENTS.md` §7. A entrada mais nova fica no topo. Cada entrada tem o commit, o comando exato da medida e
os números.

---

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
