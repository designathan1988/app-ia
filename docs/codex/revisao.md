# Revisão (escrita pelo Claude, revisor; o Codex lê e aplica, mas não edita)

O veredito mais recente fica no topo. Correções marcadas **EXIGIDO** vêm antes de qualquer outro trabalho.

---

## Revisão 0 (2026-10-01): passagem
- **Veredito:** ponto de partida. Nada a corrigir ainda.
- **Exigido:**
  1. Seguir `estado.md` → "Próxima tarefa", item 1, um mecanismo por commit, cada um com a medida DEV antes e depois
     registrada em `progresso.md`.
  2. Reportar o critério da A1 sempre como **cand@10**, não como cand@todas.
- **O que vou checar na próxima revisão:**
  - `git log` e `git diff` desde `1960f1c`;
  - `congelado.json` sem mudança;
  - o TEST não rodado antes do portão;
  - `auditoria.py` sem regra manual;
  - nenhuma regex, lista de palavras ou peso inicial por palavra novos em `nucleo/lang/`;
  - os números do diário reproduzíveis pelo comando registrado.
