# Diário de progresso (preenchido pelo Codex)

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
