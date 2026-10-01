# Instruções para o Claude (repositório nucleo)

## Leia antes de continuar
- **Memória do trabalho em curso:**
  `C:\Users\jonathanrodriguesti\.claude\projects\C--Codex-Shared-IA\memory\project-plano-d.md`.
  É o estado e o próximo passo.
- **Plano em vigor:** [docs/plano_aprendizado.md](docs/plano_aprendizado.md) (Plano D). A compreensão é aprendida
  de anotação humana pública e medida em frases escritas por outras pessoas. Depois da [auditoria](docs/auditoria.md) (2026-10-01), as etapas em vigor são a D1 e a A1–A4 (§7 do plano):
  gerar todas as ações possíveis e ranquear com um modelo log-linear aprendido, mais NENHUMA AÇÃO e limiar
  calibrado. Não se escreve mais nenhum gerador de leituras nem custo à mão.
- **Histórico, não seguir:** [docs/plano_compreensao.md](docs/plano_compreensao.md) (C0 a C6). A forma lógica, a
  ancoragem e a abdução que ele construiu continuam sendo a base. O método dele (rodadas e congelados escritos por
  mim, uma regra por classe de erro) foi abandonado.

## Como trabalhar aqui
- Python: `C:/ctv/n/Scripts/python.exe`. Testes: `pytest -q tests --ignore=tests/test_web.py`.
- **Medidas:**
  - **principal:** os conjuntos externos do Plano D (`experiments/externo/`): UD e PropBank (estrutura), DocEdit
    (ação), MASSIVE (segurança). Teste só nos portões.
  - **só regressão:** `experiments/m5_livre.py`, `experiments/m5_requests.py`, rodadas r7 a r13 e congelados v1 a
    v6. Não guiam mais o trabalho.
- **Publicação:** `git push origin main:master` (GitHub `app-ia`).
- **Regras:**
  - sem LLM, nada neural, nenhum modelo de linguagem pré-treinado; modelos lineares ou estatísticos por contagem,
    treinados aqui em anotação humana pública, são permitidos;
  - **nenhuma regra nova de construção** no código da compreensão. Uma falha nova se resolve com dados, recurso
    lexical, peso aprendido ou ensino na conversa;
  - não escrever mais rodadas nem congelados autorais como medida;
  - medida limpa antes de qualquer mudança, registrada no plano;
  - CPU: prioridade abaixo do normal, um trabalho pesado por vez.
