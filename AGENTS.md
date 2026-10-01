# AGENTS.md: instruções para o Codex (repositório nucleo)

Leia este arquivo inteiro antes de tocar em qualquer coisa. Ele substitui, para você, o `CLAUDE.md`, que é das
sessões do Claude.

## 1. O que é
O **núcleo** é um motor cognitivo local, **sem LLM**: raciocínio lógico, mundo do código e uma ponte sem interface
para o builder-6 (editor de páginas, em `C:\Codex-Shared\deepseek\builder-6`). O trabalho em curso é a
**compreensão de português e inglês dentro do domínio do builder**: um *semantic parser grounded* que aprende a
linguagem de interação com o builder. Não é um reconhecedor de comandos.

**Divisão de papéis:**
- você (Codex) **decide o caminho e implementa**;
- o Claude, numa conversa à parte, só **verifica a integridade** do seu trabalho;
- o retorno dele chega por `docs/codex/revisao.md`.

**Autonomia (decisão do usuário, 2026-10-01):** você trabalha livremente. Experimente, meça, veja se deu certo,
mude a abordagem quando não der e escolha os melhores caminhos. Isso vale para técnicas, ordem das tarefas,
componentes e até a arquitetura, quando a medida mostrar que o caminho atual não chega ao objetivo. Registre no
diário o motivo de cada mudança de rumo. Só duas coisas são fixas:
- **o objetivo:** compreender português e inglês livremente no domínio do builder, inclusive formulações nunca
  vistas, comprovado em frases que o sistema nunca viu e, sempre que possível, escritas por outras pessoas;
- **as regras da §4:** sem LLM e nada neural, nenhum conhecimento linguístico escrito à mão, medida honesta,
  conjuntos congelados e TEST só no portão, CPU, commits.

Os critérios de cada etapa estão na especificação. Diagnósticos e sugestões do revisor ou do `estado.md` são
informação, não ordens.

## 2. Leia antes de continuar (nesta ordem)
1. `docs/codex/revisao.md`: o último veredito do revisor. Ele só aponta **violação de regra ou de integridade**,
   e uma violação apontada é corrigida antes do resto. O que não for violação é só informação.
2. `docs/codex/especificacao.md`: a especificação do usuário, na íntegra. **O objetivo e as regras dela governam;
   o caminho é seu.**
3. `docs/codex/estado.md`: o ponto de partida da passagem (números, falhas, diagnóstico). Não é uma lista de
   ordens.
4. `docs/codex/progresso.md`: o diário. Continue a partir da última entrada.

Para contexto técnico, só se precisar:
- `docs/roteiro_ccg.md`: técnicas e fontes (CCG, UBL/FUBL, Artzi & Zettlemoyer);
- `docs/auditoria.md`: por que o motor antigo estagnou;
- `docs/plano_aprendizado.md`: medidas externas (UD, DocEdit, MASSIVE).

`docs/plano_compreensao.md` é histórico e não deve ser seguido.

## 3. Mapa do código
| Onde | O quê |
|---|---|
| `nucleo/lang/esquema.py` | `ActionSchema` descoberto do próprio builder (manifest, i18n, efeitos observados) |
| `nucleo/lang/ir.py` | IR independente de língua (`Ref`, `Value`, `Action`, `Plan`, `canonical`) |
| `nucleo/lang/mundo.py` | grounding tipado da IR, `Discourse` (estado discursivo), `Sandbox` (execução no builder sem interface), `same_state` |
| `nucleo/lang/acoes_ranker.py` | gerador hierárquico e ranqueador aprendido (perceptron estruturado médio) |
| `nucleo/lang/evidencia.py` | evidência lexical **com origem** (catálogo, WordNet/ILI, valores, Wiktionary, numerais) |
| `nucleo/lang/ccg/` | λ-cálculo tipado, CCG, UBL/FUBL, IBM1: base para a A2 (composição) |
| `experiments/a1/` | corpus (`treino.py`, `dev.py`, `teste.py`, `holdout.py`, `contrastes.py`, `dialogos.py`, `paginas.py`), `avaliar.py`, `auditoria.py`, `congelado.json` |
| `nucleo/lang/interpret.py`, `ground.py`, `understand.py` | **motor antigo**, com geradores e custos escritos à mão. Ainda é o que a web usa. Vai ser substituído (spec §20) e não deve ser estendido. |
| `nucleo/session.py`, `nucleo/assistant.py`, `nucleo/web_ui.py` | sessão, diálogo e web (porta 8790). A entrada é `interpret.understand_request` |
| `nucleo/builder/` + `bridge/builder/` | ponte para o builder-6 real (Node + Vite), planejador |
| `data/` | dados e caches; `data/externo` e `data/cache` não vão para o git |

## 4. Regras permanentes do usuário (não negociáveis)
- **Nenhum LLM**, de nenhum tipo, nem modelo de linguagem pré-treinado, nem API externa para compreender.
  - Modelos treinados aqui só podem ser **lineares ou estatísticos por contagem**. Nada neural.
- **Nenhum conhecimento linguístico em código**, nem em JSON, YAML ou TS:
  - regex de intenção;
  - `if`/`switch` que associa palavra ou frase a ação;
  - listas de paráfrases;
  - tabelas de sinônimos escritas à mão;
  - pesos iniciais escritos à mão para uma palavra.

  Condicionais puramente algorítmicos são permitidos.
- **Sem remendos.** Uma falha é classificada numa das categorias da spec 2, §14, e corrigida **no mecanismo
  responsável**: dados, recurso lexical externo, traço, peso aprendido, esquema ou busca. Nunca com tratamento
  para a frase que falhou.
- **O corpus não é catálogo.** Não se resolve cobertura acrescentando formas de pedir ao TRAIN (spec 2, §3).
- **Medida honesta:**
  - o gold nunca entra na geração nem na avaliação;
  - a medida é limpa, feita antes das correções;
  - todo número vem de execução real e é registrado com o comando que o produziu;
  - números ruins também são reportados.
- **Conjuntos congelados** (`experiments/a1/congelado.json`, com hash de **todos**: TRAIN, DEV, TEST, HOLDOUT,
  CRUZADO, CONTRASTE e DIALOGOS):
  - não edite nenhum deles e nunca rode `--recongelar`. O `avaliar.py` aborta se um hash mudar, e é assim que deve
    ser;
  - se o mecanismo realmente precisar de mais dados de treino, eles vêm de fonte externa ou do próprio builder, num
    conjunto **novo** e separado. A justificativa vai no diário, e o revisor precisa aprovar antes;
  - o **TEST roda só no portão da A1**, uma vez, quando o DEV estiver pronto (avaliação completa, sem `--dev`), e o
    resultado é registrado no diário. Depois disso, nada é ajustado olhando erros individuais do TEST.
- **CPU:**
  - todo processo pesado roda em prioridade abaixo do normal. Os scripts chamam
    `SetPriorityClass(GetCurrentProcess(), 0x4000)`; faça o mesmo em scripts novos;
  - **um trabalho pesado por vez**;
  - não deixar processos órfãos.
- **Não reportar nem perguntar à toa.** Continue até concluir a etapa. Pare só quando:
  - um portão falhar: nesse caso relate os números, a análise de erro e a causa, sem remendo;
  - houver uma decisão que só o usuário pode tomar.
- **Nunca escrever** "o usuário pode testar" sem que a web (porta 8790) esteja de fato usando o motor novo.

## 5. Ambiente
- Python: `C:/ctv/n/Scripts/python.exe`. É Python 3.12 puro: sem numpy e sem torch. **Não instalar** pacotes
  pesados.
- Testes: `C:/ctv/n/Scripts/python.exe -m pytest -q tests --ignore=tests/test_web.py`.
- Avaliação da A1:
  - desenvolvimento, só DEV, com cada falha listada:
    `C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py --dev > data/cache/a1_dev.log`. O treino leva cerca de
    165 s;
  - completa, **só no portão**: `C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py`. Mede TEST, holdout,
    contrastes, diálogos, custo e ablações, e grava `data/cache/a1_relatorio.json`. Leva bem mais tempo; rode uma
    vez só.
- Auditoria de regras escondidas: `C:/ctv/n/Scripts/python.exe experiments/a1/auditoria.py`, que gera
  `data/cache/a1_auditoria.json`. Rode antes de cada commit que mexa em `nucleo/lang/`.
- A ponte do builder usa Node e o builder-6 em `C:\Codex-Shared\deepseek\builder-6`. **Não altere o builder-6.**
- Web: `python run_web.py`, na porta 8790.
- Ao escrever arquivos com acentos, use UTF-8. Os textos do corpus estão em UTF-8.

## 6. Git: preservar o trabalho
- Branch local `main`; o remoto é o GitHub `app-ia`, branch `master`. A publicação é **`git push origin main:master`**.
- **Um commit por passo concluído**, pequeno e coerente, com os testes passando. A mensagem vai em **inglês** e
  diz o que mudou e o número medido, se houver.
- Push depois de cada commit. Se o sandbox bloquear a rede, registre "push pendente" no diário e continue; o
  revisor publica depois.
- Proibido:
  - force-push;
  - `reset --hard`;
  - reescrever o histórico;
  - commitar `data/externo` ou `data/cache`;
  - apagar trabalho de outra pessoa.
- Não commite `docs/codex/revisao.md`: quem escreve esse arquivo é o revisor.

## 7. Diário (`docs/codex/progresso.md`)
Ao fim de **cada** passo, acrescente uma entrada **no topo**, abaixo do cabeçalho:
```
### AAAA-MM-DD HH:MM: <título curto>
- Commit: <hash curto> (push: ok | pendente)
- O que mudou: <arquivos/mecanismo; qual categoria de erro foi atacada (spec 2 §14)>
- Medida: `<comando exato>` → <números: cand@1/3/5/10, rank@1/3/5, ir/action/state, n>
- Falhas restantes: <lista curta com categoria>
- Próximo passo: <uma frase>
```
O revisor avalia por este diário e pelo `git log`. Uma entrada sem comando e sem número não conta como progresso.

## 8. Comunicação com o usuário

Estas regras valem em todas as sessões e complementam a autonomia da seção 4: narrar o trabalho não significa
parar para pedir permissão ou esperar uma resposta.

1. Antes de começar cada passo, escreva de 1 a 3 frases, em português simples: o que vai fazer, por quê (qual
   falha ou mecanismo está atacando) e como vai saber se deu certo.
2. Antes de rodar algo demorado (treino, avaliação ou testes), avise o que vai rodar e quanto tempo deve levar.
3. Ao terminar cada medida, mostre **cand@10, rank@1 e IR/ação/estado**, comparados com a medida anterior, e diga
   em uma frase se melhorou, piorou ou ficou igual, e por quê. Se a causa ainda não estiver demonstrada, diga isso.
4. A cada commit, diga o hash e resuma em uma frase o que foi preservado.
5. Se algo der errado ou mudar de plano, diga na hora o que aconteceu e o que fará em seguida.
6. Nunca fique mais de alguns minutos sem dar notícia. Se estiver esperando um processo, diga isso.
7. Ao fim de cada etapa, faça um resumo curto: o que foi feito, os números atuais, o que falta para a A1 passar
   (meta: **cand@10 ≥ 95%**) e o próximo passo.

Continue trabalhando sem parar para pedir permissão; a comunicação acompanha a execução.
