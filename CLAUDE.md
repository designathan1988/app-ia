# Instruções para o Claude (repositório nucleo)

## Papel atual (desde 2026-10-01): revisor do Codex
- A implementação passou para o **Codex**. As instruções dele estão em `AGENTS.md` e `docs/codex/`:
  `especificacao.md` (a especificação do usuário, que governa), `estado.md`, `progresso.md` (diário do Codex) e
  `prompt_inicial.md`.
- **O Codex trabalha livremente** (decisão do usuário, 2026-10-01). Ele escolhe técnicas, ordem e abordagem, e pode
  mudar de abordagem. O Claude **não delimita escopo nem dita passos**: nada de prazos, ordens de tarefa ou
  critérios de método inventados por ele.
- O Claude só **verifica a integridade**, e só nos marcos (portão, fim de etapa, mudança grande de abordagem) ou
  quando o usuário pedir. A cada revisão:
  - `git log` e `git diff` desde a anterior;
  - integridade: `experiments/a1/congelado.json` intacto, TEST só no portão, sem injeção do ouro;
    `experiments/a1/auditoria.py` limpo; grep de regras linguísticas novas;
  - conferir os números do diário.

  O veredito vai em `docs/codex/revisao.md`, com commit próprio e push.
- Sem treinos nem testes longos durante as revisões.

## Leia antes de continuar
- **Memória do trabalho em curso:**
  `C:\Users\jonathanrodriguesti\.claude\projects\C--Codex-Shared-IA\memory\project-plano-d.md`.
  É o estado e o próximo passo.
- **Plano em vigor:** [docs/plano_aprendizado.md](docs/plano_aprendizado.md) (Plano D). A compreensão é aprendida
  de anotação humana pública e medida em frases escritas por outras pessoas. Em vigor: o **roteiro CCG** [docs/roteiro_ccg.md](docs/roteiro_ccg.md) (2026-10-01): léxico CCG induzido
  (UBL/FUBL, Kwiatkowski et al.), aprendizado pela execução (Artzi & Zettlemoyer). Etapas E0 a E6 com prazos e
  portões, comprovadas primeiro por replicação (GeoQuery, MATIS pt/en). Não se escreve mais nenhum gerador de leituras nem custo à mão.
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
