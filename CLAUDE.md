# Instruções para o Claude (repositório nucleo)

## Leia antes de continuar
- **Memória do trabalho em curso:**
  `C:\Users\jonathanrodriguesti\.claude\projects\C--Codex-Shared-IA\memory\project-compreensao-reconstrucao.md`.
  É o estado e o próximo passo.
- **Plano em vigor:** [docs/plano_compreensao.md](docs/plano_compreensao.md), a reconstrução da compreensão
  (etapas C0 a C6 com portões).
- **Projeto do significado:** [docs/significado.md](docs/significado.md). Semântica formal do núcleo lógico:
  [docs/semantica.md](docs/semantica.md).

## Como trabalhar aqui
- Python: `C:/ctv/n/Scripts/python.exe`. Testes: `pytest -q tests --ignore=tests/test_web.py`.
- **Medidas:**
  - `experiments/m5_livre.py` (frases livres, regressão);
  - `experiments/m5_requests.py` (bateria do M5);
  - `experiments/congelado.py` (conjunto congelado; **só nos portões**; não ajustar com base nele).
- **Publicação:** `git push origin main:master` (GitHub `app-ia`).
- **Regras:**
  - sem LLM;
  - sem remendos frase a frase;
  - o código novo da compreensão vai nos módulos novos (`nucleo/lang/logic_form.py` e seguintes), não em mais
    padrões em `understand.py`.
