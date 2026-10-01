# AGENTS.md: instruções para o Codex (repositório nucleo)

Leia este arquivo inteiro antes de tocar em qualquer coisa. Ele substitui, para você, o `CLAUDE.md`, que é das
sessões do Claude.

## 0. Missão e modo de trabalho

**Instrução definitiva do usuário (2026-10-01): esta seção prevalece sobre orientações anteriores de ritmo,
ordem ou parada.** O trabalho continua até a missão estar comprovadamente entregue.

**Pronto** significa que a web na porta **8790** compreende pedidos em português e inglês sobre o builder,
inclusive formulações e palavras ausentes do treino; executa quando há confiança calibrada, pergunta com **2 ou
3 opções** quando não há, apresenta **no máximo 0,5% de execuções erradas** e aprende com a escolha do usuário.
A prova exige um **teste novo**, congelado por hash antes de qualquer medida e usado uma única vez no portão,
e medidas em frases de outras pessoas: **DocEdit dev e MASSIVE dev PT/EN**. Reporte também cobertura de execução,
abstenções e limites da medida; não satisfaça a meta de erro simplesmente recusando tudo.

**Autonomia total:** escolha abordagem, arquitetura, técnicas e ordem. Um portão reprovado exige diagnóstico e
mudança de rumo, **não parada**. Registre o motivo no diário e continue sem esperar revisor ou permissão; o
revisor só confere integridade. A1–A4 são marcos, não uma sequência obrigatória nem condição de parada.

**Causa de fundo:** o resultado A1 (DEV 95,0 contra TEST 67,2 de cand@10, vocabulário não visto 47,4 e falhas de
composição/elipse) é diagnóstico. Não ajuste mais ao DEV antigo. Use novos dados de treino não escritos à mão:
DocEdit train, enunciados canônicos derivados dos rótulos do builder, paráfrases de recursos externos,
supervisão por execução e escolhas reais do usuário. Novos conjuntos ficam separados dos congelados; fontes,
proveniência, divisões e prevenção de vazamento devem ser registradas. Essa obtenção de dados já está autorizada.

**Velocidade com rigor:** trabalhe diretamente, sem subagentes, conforme a instrução posterior do usuário.
Mantenha um único processo pesado por vez, em prioridade abaixo do normal. Use
triagem barata; avaliações completas ficam para marcos e ablações são executadas separadamente. Hipóteses sem
ganho são descartadas; ganhos medidos e verificados recebem commit e push imediatamente, com diário junto.

**Antes de cada commit:** cumpra a definição de pronto da §9, rode `scripts/verificar.py` e revise o
diff contra este arquivo e `docs/codex/especificacao.md`, sem delegar. Corrija as brechas antes de publicar.
Verifique consumidores compartilhados, suíte inteira, auditoria, congelados, determinismo e condições das medidas.

**Integração:** ligue o motor novo à web assim que superar o antigo nas medidas externas, com a política de
execução/pergunta validada. Comunique em cada marco os números externos e o que funciona ou não na web.
As regras de comunicação da §8 valem durante todo o trabalho.

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
  vistas, comprovado em teste novo e nas medidas externas humanas exigidas na §0;
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
  - novos dados de treino externos ou derivados do builder ficam em conjuntos **novos e separados**, com fonte,
    justificativa e proteção contra vazamento no diário; não dependem de aprovação prévia do revisor;
  - o **TEST A1 já foi consumido no portão**. Não o execute novamente nem ajuste usando seus erros individuais;
  - cada novo teste é congelado por hash antes de qualquer medida e usado uma única vez em seu portão.
    Use novos dados de treino e desenvolvimento externo para decidir; não use o DEV A1 já inspecionado para ajustar.
- **CPU:**
  - todo processo pesado roda em prioridade abaixo do normal. Os scripts chamam
    `SetPriorityClass(GetCurrentProcess(), 0x4000)`; faça o mesmo em scripts novos;
  - **um trabalho pesado por vez**;
  - não deixar processos órfãos.
- **Continue até a missão estar entregue.** Portão reprovado é evidência para mudar de rumo, não motivo para
  parar ou esperar permissão. Mantenha os avisos da §8 e registre as decisões no diário.
- **Nunca escrever** "o usuário pode testar" sem que a web (porta 8790) esteja de fato usando o motor novo.

## 5. Ambiente
- Python: `C:/ctv/n/Scripts/python.exe`. É Python 3.12 puro: sem numpy e sem torch. **Não instalar** pacotes
  pesados.
- Testes: `C:/ctv/n/Scripts/python.exe -m pytest -q tests --ignore=tests/test_web.py`.
- Avaliação A1 histórica, já concluída: comandos e números estão em `docs/codex/relatorio_a1.md`.
  Não repetir seu TEST nem continuar ajustando seu DEV. Próximas avaliações devem separar treino, triagem,
  calibração e teste novo congelado; executar ablações à parte dos portões.
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

A entrada deve estar **no mesmo commit da mudança** (§9). Como o hash desse commit só existe depois de criá-lo,
use `Commit: este commit — <título exato>` na entrada nova; o histórico/Git blame identifica o hash. Informe o
hash e o resultado real do push na comunicação. Não reescreva o histórico para inserir o próprio hash nem declare
um push como concluído antes de executá-lo. Entradas retrospectivas continuam usando o hash conhecido.

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

## 9. Definição de pronto

Antes de **cada commit**, todas as condições abaixo precisam estar satisfeitas:

1. **Suíte inteira passando:** execute
   `C:/ctv/n/Scripts/python.exe -m pytest -q tests --ignore=tests/test_web.py`.
   Testes focados complementam essa execução; não a substituem. O resultado deve corresponder ao código que
   será commitado, incluindo arquivos novos. Uma alteração posterior invalida a verificação afetada.
2. **Consumidores verificados:** confira o efeito em tudo que usa o módulo alterado, incluindo motor antigo,
   motor novo, sessão e web. Identifique os consumidores e verifique seus contratos com os testes/checagens
   pertinentes. A métrica A1 sozinha não comprova compatibilidade; a suíte acima exclui `test_web.py` e não
   demonstra, por si só, que a web usa o motor novo.
3. **Auditoria de regras escondidas:** deve estar limpa, ou cada achado deve ter identificação e justificativa
   registradas no diário e revisadas. Uma justificativa de falso positivo não autoriza regra linguística manual.
   Mudanças no motor exigem auditoria correspondente à versão verificada; no portão, todos os conjuntos são
   cobertos pela auditoria da própria avaliação.
4. **Integridade e reprodução:** `congelado.json` e os conjuntos congelados permanecem intactos. O treino deve
   continuar determinístico. Não use uma semente fixa para esconder dependência da ordem de iteração.
5. **Condições das medidas:** cite somente números realmente medidos, com comando exato, corpus, configuração
   e condições identificáveis. Separe latência com/sem perfilador. Resultados antigos ou de outra versão não
   validam silenciosamente a mudança atual.
6. **Diário no mesmo commit:** inclua uma entrada nova com o título que identifica o commit, o motivo da mudança,
   arquivos/mecanismo afetados, comandos exatos, números, falhas restantes e próximo passo. Mudanças documentais
   não pedem novo DEV; registre a checagem documental e identifique como anteriores os últimos números do motor.
7. **Salvar o ganho:** mediu, verificou, faça commit e push. Não acumule ganho validado fora do Git enquanto testa
   outras hipóteses. O commit inclui código, testes e diário; informe imediatamente o hash e o resultado do push.

**Verificação automatizada:** rode `scripts/verificar.py` antes de cada commit, com o título e os arquivos que
pretende publicar. O modo normal exige a suíte completa e produz um comprovante vinculado aos arquivos
verificados. `--rapido` serve somente para diagnóstico e nunca aprova um commit. Faça o stage somente depois da
verificação e use `--confirmar` com o comprovante para conferir os blobs exatos do índice antes de commitar.
Após os checks passarem, o script acrescenta na entrada do diário a linha de verificação com os resultados
reais do JUnit; essa escrita própria é incluída no comprovante final. Ele não faz stage, commit ou push.
Não inclua `docs/codex/revisao.md`, conjuntos congelados, `data/cache` ou `data/externo` no commit.

**Revisão antes de publicar:** revise diretamente o diff contra este arquivo e a especificação, procurando
regras linguísticas escondidas, vazamento, efeitos colaterais, medidas em condições inválidas e diário
incompleto. Corrija antes de publicar. A instrução posterior do usuário proíbe subagentes.

As verificações pesadas continuam sequenciais, em prioridade abaixo do normal.

## 10. Pesquisa proporcional à execução

A instrução posterior do usuário substitui o protocolo de pesquisa longa: pesquise na internet somente o
necessário para fazer certo, use fontes primárias e registre a fonte de dados e decisões relevantes no diário.
Não prolongue preparação nem use subagentes. Resultados publicados não substituem medidas deste motor.

**Direção vigente de implementação:** os dados automáticos (rótulos do builder, recursos lexicais externos,
DocEdit train e MASSIVE como nenhuma ação) são treino adicional para o motor A1 com IR, grounding e ranking
estruturado. Não substituí-lo por classificação bag-of-words de comandos inteiros. O caminho `contagem.py` e
`experiments/novo` foi retirado, e não deve ser ligado à web. O teste novo deve conter pedidos naturais de
pessoas, jamais somente rótulos ou frases de molde. Preserve todo teste já consumido e não o reutilize para ajuste.
