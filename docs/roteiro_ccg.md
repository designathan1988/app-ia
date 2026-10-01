# Plano: compreensão de português e inglês por mapeamento aprendido da língua (CCG + léxico induzido)

## Contexto
**O pedido.** O usuário quer que a aplicação entenda português e inglês em linguagem natural e converse, sem
condicionais, regex, inventário de comandos nem remendos. Pede um roteiro fechado: objetivos mensuráveis, técnicas,
fontes, evidências, materiais, testes de simulação e prazos.

**Por que não funciona hoje.** A auditoria (`nucleo/docs/auditoria.md`) mostrou que nenhuma palavra é ligada a
significado por aprendizado: tudo está escrito à mão.
- Em pedidos de edição reais (DocEdit dev, 908 frases em inglês): 8,6% certos, 2,2% executados errado, 89% "não
  entendi" ou pergunta.
- O caminho certo já estava na pesquisa do projeto (`docs/pesquisa.md` §B; `docs/plano.md` §1): induzir o léxico a
  partir de pares (frase, significado), com viés indutivo explícito. Eu não o segui.

Este plano implementa esse caminho. Antes de tocar no builder, a técnica é **comprovada por replicação** de
resultados publicados.

## 1. Objetivos mensuráveis (com prazo)
| # | Objetivo | Medida | Meta | Prazo |
|---|---|---|---|---|
| O1 | A implementação reproduz o estado da arte publicado | GeoQuery Geo880, teste (280), λ-cálculo, F1 exato | ≥ 85,0 (publicado: UBL 88,2; FUBL 88,6) | 2026-10-07 |
| O2 | Independência de língua, com português incluído | MATIS (MultiATIS++), mesmas formas lógicas em pt e en, teste | acerto exato em pt ≥ acerto em en − 5 pontos | 2026-10-09 |
| O3 | Pedidos reais ao builder, em inglês | DocEdit dev: tipo de ação certo na melhor leitura | ≥ 70% (hoje 33%) | 2026-10-19 |
| O4 | Nunca executar errado em silêncio | DocEdit dev e MASSIVE dev pt/en: execuções erradas | ≤ 0,5% (hoje 2,2% / 0,7% / 0,9%) | 2026-10-19 |
| O5 | Aprender uma forma nova de pedir na conversa | simulação de usuário: forma não vista → pergunta → escolha → mesma forma executada | ≥ 90% das formas aprendidas depois de 1 escolha; 0 regressões | 2026-10-22 |
| O6 | Sem regra à mão no caminho frase → significado | grep e revisão: geradores, `COST`, `LIMIT`, `FRAME_COMMANDS`, `STATE_OF_FRAME`, verbos de `frames.json` removidos | 0 restantes | 2026-10-23 |

**Fora do escopo, dito sem rodeio:**
- Conversa aberta sobre qualquer assunto do mundo exige conhecimento de mundo que o sistema não tem.
- O escopo é conversar sobre o que o sistema representa: página e builder, código, fatos ditos pelo usuário.
  Inclui pedidos, perguntas, afirmações e referências entre turnos.

## 2. Técnica e evidência publicada (verificada nos artigos)
| Técnica | O que faz | Resultado publicado | Fonte |
|---|---|---|---|
| **CCG probabilística** com léxico (palavra → categoria : termo λ) e poucos combinadores universais | compõe o significado da frase a partir do significado das palavras, igual em todas as línguas | base de todos abaixo | Steedman, *The Syntactic Process*, MIT 2000 |
| **UBL**: indução do léxico por unificação de ordem superior (divide o significado da frase em pedaços ligados a trechos da frase), perceptron/gradiente com derivação latente, inicializado por IBM Model 1 | aprende o léxico de pares (frase, forma lógica), sem moldes por língua | Geo880 λ: P 94,1 / R 85,0 / F1 89,3; Geo250 em inglês, espanhol, japonês e turco: F1 78–85 | Kwiatkowski, Zettlemoyer, Goldwater, Steedman, EMNLP 2010, [D10-1119](https://aclanthology.org/D10-1119/) |
| **FUBL**: léxico fatorado em lexemas (palavra → constantes) × moldes (como entram na composição) | generaliza o uso de uma palavra para construções nunca vistas; lida com fala espontânea | ATIS (fala espontânea, 4.480 pares) teste: exato 82,8, parcial F1 94,6; Geo880 F1 88,6; "6% das análises usam itens nunca vistos" | Kwiatkowski et al., EMNLP 2011, [D11-1140](https://aclanthology.org/D11-1140/) |
| **Aprender executando** (validação pelo estado final), com léxico-semente de 141 entradas | aprende sem forma lógica anotada, só vendo se a execução deu certo | SAIL: 64–65% contra 54–57% do estado da arte anterior; corpus limpo: 77,6–78,6% por frase | Artzi & Zettlemoyer, TACL 2013, [Q13-1005](https://aclanthology.org/Q13-1005/) |
| **DCS**: composição sobre árvore de dependências, aprendida de respostas | sem formas lógicas anotadas | Geo880: 91,1 | Liang, Jordan, Klein, ACL 2011, [P11-1060](https://aclanthology.org/P11-1060/) |
| **Naturalização pelo uso** | usuários ensinam sintaxe nova por definição | 85,9% dos últimos 10 mil comandos usaram linguagem ensinada | Wang, Ginn, Liang, Manning, ACL 2017, [arXiv:1704.06956](https://arxiv.org/abs/1704.06956) |
| **Aprendizado entre situações** | o significado da palavra sai da consistência entre várias situações ambíguas | modelos e experimentos humanos | Siskind 1996; Kwiatkowski et al., EACL 2012 |
| **Viés indutivo** (Mitchell 1980); **princípio do tamanho** (Xu & Tenenbaum 2007) | generalizar exige viés declarado: preferir a hipótese mais específica consistente com os dados | teoria e experimentos | `docs/pesquisa.md` §B |
| **RL para instruções → ações** (ajuda do Windows) | log-linear treinado pela recompensa do ambiente | rivaliza com o supervisionado com poucos ou nenhum exemplo anotado | Branavan et al., ACL 2009, [P09-1010](https://aclanthology.org/P09-1010/) |

**Por que a meta é alcançável:** as técnicas acima chegam a 78–89% em domínios do mesmo tamanho que o builder, com
600 a 4.500 pares, e funcionam em várias línguas. Nenhuma usa rede neural ou LLM: são modelos log-lineares mais um
léxico simbólico.

## 3. Arquitetura
**Viés indutivo** (a única parte escrita à mão; universal, nunca por frase ou por comando):
1. **Tipos:** e (elemento), t (verdade), i (número), v (valor), p (propriedade), k (tipo de elemento), ev (ação),
   mais tipos de função. As constantes são **lidas do builder**:
   - 263 comandos com argumentos tipados (`manifest/commands`);
   - 61 tipos de elemento e 181 propriedades;
   - 88 atributos;
   - valores pela gramática do W3C.

   Reusa `builder/scenarios.load_commands`, `builder/knowledge.load_domains`, `lexicon._load` e `values`.
2. **Constantes lógicas:** ι (definido), A (indefinido / novo), ∀, ¬, igualdade, comparação, sequência; os atos
   fazer!, perguntar? e afirmar.
3. **Combinadores CCG:** aplicação (>, <), composição (>B, <B), coordenação e elevação de tipo (4 regras, como
   Artzi & Zettlemoyer 2013 §6.3).
4. **Restrições da divisão** (UBL §4.1): sem variáveis vazias, coordenação limitada a N=4, aplicação limitada.
5. **Inicialização dos pesos:**
   - IBM Model 1 (contagem, EM) entre palavras e constantes;
   - o grafo de conceitos pt/en (`concepts.meanings`) como priori.

   Os dois são probabilidades iniciais, nunca portões.

**O que é aprendido:**
- **lexemas**: palavra ou expressão → constantes, em pt e en;
- **moldes**: como o lexema entra na composição;
- **pesos** do modelo log-linear: traços de lexema, molde, par lexema-molde, predicado-argumento e
  predicado-tipo, como FUBL §8;
- **palavras funcionais** (artigo, negação, quantificador, interrogativo, modo): aprendidas como os demais lexemas.
  Os traços UD dos treebanks (`Definite`, `Polarity=Neg`, `PronType`, `Mood`) entram como priori.

**Execução:** a forma lógica é avaliada sobre a página (`World`). A ação vira restrições no formato de hoje
(`style/field/added/removed/moved/command`) e passa pelo planejador que já existe (`nucleo/builder/planner.py`).
- Perguntas são avaliadas sobre a página e sobre o Datalog (M1).
- Afirmações viram fatos no Datalog.

**Decisão:**
- p(forma lógica | frase) vem do modelo, somando as derivações.
- Executar só acima de θ, calibrado no dev para ≤ 0,5% de erros.
- Abaixo de θ, perguntar mostrando as 2 ou 3 melhores formas, parafraseadas. A escolha vira par de treino
  imediato, com validação como em Artzi 2013.

## 4. Materiais e ferramentas
| Material | Uso | Situação |
|---|---|---|
| GeoQuery Geo880 em λ (600 treino / 280 teste), via XSemPLR `dataset/mgeoquery` (en + 7 línguas; λ, Prolog, FunQL, SQL) | replicação O1 | baixar (~1 MB) |
| MATIS (MultiATIS++), via XSemPLR `dataset/matis`: as mesmas frases em en, pt, es, de, fr, zh com SQL (444 de teste em pt) | prova em português O2. O SQL vira termo sem variáveis por conversão mecânica (árvore do SQL) | baixar (~6 MB) |
| Manifest e i18n do builder-6 (2.098 chaves pt/en; rótulos com lacunas; 388 mensagens de status) | constantes e tipos; pares-semente (rótulo ↔ operação) | local |
| Frases rotuladas já escritas (~1.000: `experiments/rodada*.py`, `congelado*.py`, cenários `tests/gen/requests.py`) | treino supervisionado do domínio | local |
| DocEdit train/val (12.464 / 1.780) | treino com validação fraca (tipo de ação); dev/teste para O3 | local |
| MASSIVE 1.1 pt-PT/en-US | negativos no treino; dev/teste para O4 | local |
| Grafo ILI pt/en (`data/cache/conceitos.sqlite`), kaikki pt, MorphoBr, lemas do EWT | priori lexical; morfologia (lema como traço) | local |
| Treebanks UD (Bosque, PetroGold, Porttinari, EWT) e analisador D1 (`parser_rotulado.py`) | priori das palavras funcionais; traço de dependência | local |
| Referência de implementação: Cornell SPF ([github.com/lil-lab/spf](https://github.com/lil-lab/spf), Java) | consulta do algoritmo (UBL/FUBL/GENLEX); o código não é usado | consulta |
| Python 3.12 puro (`C:/ctv/n`), `perceptron.py`, prioridade abaixo do normal | toda a implementação | local |

## 5. Roteiro (cada etapa tem simulação, critério numérico e prazo; portão reprovado = parar e relatar, sem remendo)
| Etapa | Entrega | Teste de simulação | Critério | Prazo |
|---|---|---|---|---|
| **E0 Replicação** | `nucleo/lang/ccg/`: `logica.py` (termos λ tipados, β-redução, unificação restrita), `ccg.py` (categorias, combinadores, CKY com feixe), `ubl.py` (divisão, NEW-LEX, fatoração FUBL, gradiente), `ibm1.py`; `experiments/externo/geo.py` | treinar em Geo880 (600) e testar nos 280 | F1 ≥ 85,0 (O1). Mesmo protocolo em alemão (MGeoQuery de): F1 ≥ en − 8 | 2026-10-07 |
| **E0b Português** | `experiments/externo/matis.py` (SQL → termo; mesmo learner) | treinar e testar MATIS en e pt separadamente | pt ≥ en − 5 (O2) | 2026-10-09 |
| **E1 Esquema** | `nucleo/lang/ccg/esquema.py`: tipos e constantes do builder; executor forma lógica → restrições, ligado ao `World` e ao planejador | todas as 263 operações têm tipo; formas lógicas-ouro das ~1.000 frases rotuladas executam e chegam às restrições esperadas | 100% das operações tipadas; ≥ 98% das formas-ouro executam certo | 2026-10-12 |
| **E2 Dados** | `experiments/externo/pares.py`: rótulos i18n → (frase, forma); frases rotuladas → (frase, forma); DocEdit → (frase, validação por tipo de ação); MASSIVE → (frase, nenhuma ação) | contagens e auditoria de vazamento | 0 frases de dev ou teste no treino; contagens registradas | 2026-10-13 |
| **E3 Domínio** | treino do léxico no domínio do builder (pt e en juntos; validação como Artzi 2013 para o DocEdit) | dev: DocEdit, MASSIVE, metade das frases rotuladas guardada | DocEdit tipo de ação ≥ 70% (O3); frases rotuladas guardadas ≥ 85% | 2026-10-17 |
| **E4 Decisão** | θ calibrado; perguntas com opções; `understand_request` → novo motor, mantendo `Understanding` e `Reading` | DocEdit dev e MASSIVE dev pt/en | erro ≤ 0,5% (O4); `pytest` verde | 2026-10-19 |
| **E5 Conversa** | `Session._continue_dialogue` e `Assistant.undo` gravam (frase, escolha, recusadas) → atualização online; afirmações → Datalog; perguntas pelo mesmo motor | **usuário simulado**: 200 formas não vistas (as frases rotuladas guardadas); cada falha recebe a escolha certa, e depois se testa a mesma forma e uma paráfrase | ≥ 90% aprendidas após 1 escolha (O5); 0 regressões no resto | 2026-10-22 |
| **E6 Limpeza e portão** | remoção dos geradores, `COST`, `LIMIT`, `FRAME_COMMANDS`, `STATE_OF_FRAME`, verbos de `frames.json` e `understand.py`; documentação | testes do DocEdit, MASSIVE e UD medidos **uma vez**; ponta a ponta na web (preview "nucleo", porta 8790) em pt e en | O6; números registrados em `docs/plano_aprendizado.md` | 2026-10-23 |

**Se um portão falhar:** paro na etapa, registro os números, a análise de erro por traço ou lexema e a causa.
Apresento isso antes de seguir. Nenhuma regra à mão entra para passar um portão.

## 6. Riscos conhecidos (com evidência) e resposta prevista
- **Custo da busca de léxico** (Artzi 2013: "~100k entradas por frase").
  - Resposta: análise grossa-para-fina por tipo (Artzi 2013 §8).
  - Também feixe por célula, como em UBL e FUBL.
- **Precisão menor que recall com léxico fatorado** (FUBL §9).
  - Resposta: a decisão usa θ calibrado; o que está abaixo vira pergunta (O4).
- **Morfologia rica do português** (UBL §8 e FUBL §10: variantes aprendidas separadamente).
  - Resposta: lexema sobre o lema MorphoBr, e a forma flexionada como traço.
- **Velocidade em Python puro.**
  - Resposta: frases ≤ 25 tokens; feixe limitado.
  - Medir s/frase em E0; o portão de E4 exige ≤ 0,5 s/frase.

## 7. Arquivos
- **Novos:**
  - `nucleo/lang/ccg/{logica,ccg,ibm1,ubl,esquema,motor}.py`;
  - `experiments/externo/{geo,matis,pares}.py`;
  - `tests/test_ccg_logica.py`, `test_ccg_parse.py`, `test_ubl.py`, `test_esquema.py`, `test_motor.py`.
- **Alterados:**
  - `nucleo/lang/interpret.py`: `understand_request` chama o motor;
  - `nucleo/session.py` e `nucleo/assistant.py`: gravam interações;
  - `nucleo/lang/dialogue.py`: opções estruturadas;
  - `nucleo/lang/questions.py`.
- **Removidos em E6:** os geradores de `interpret.py`; `COST` e `LIMIT` de `base.py`; `builder_commands.py`;
  os verbos de `frames.json`; `understand.py`.
- **Documentação:**
  - `docs/plano_aprendizado.md` (§7 → este roteiro, com os números de cada portão);
  - `docs/auditoria.md`;
  - os dois `CLAUDE.md`;
  - a memória `project-plano-d.md`.

## 8. Verificação
- **Por etapa:** o teste de simulação da tabela da §5, com o comando registrado e o resultado gravado em
  `data/cache/externo_*`.
- **Sempre:** `pytest -q tests --ignore=tests/test_web.py`.
- **Ponta a ponta:** web (porta 8790), em pt e en:
  - pedidos variados;
  - pergunta com opções e escolha;
  - repetir a forma nova;
  - afirmar um fato e perguntar sobre ele.
- **Testes externos** (DocEdit, MASSIVE, UD): só no portão final, uma vez.
