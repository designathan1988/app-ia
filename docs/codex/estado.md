# Estado na passagem para o Codex (2026-10-01)

Este é o ponto de partida. A partir daqui, o estado vivo fica em `progresso.md`.

## Onde o trabalho parou
- **Commit `1960f1c`** (igual a `origin/master`). A árvore está limpa.
- **Etapa: A1** da especificação (`especificacao.md`). Estão prontos o listador e o ranqueador de ações sobre o
  `ActionSchema` extraído do builder, a IR, o grounding tipado, a execução em sandbox e o corpus TRAIN/DEV/TEST
  congelado. **A A1 não está concluída.**
- **A web e a sessão ainda usam o motor antigo** (`interpret.py`). O motor novo só roda dentro de
  `experiments/a1/avaliar.py`. A troca entra na A4, pela spec §20 e por `roteiro_ccg.md` E4. Até lá, ninguém deve
  dizer ao usuário que ele já pode testar o motor novo.

## O que existe (não reinicie a arquitetura: spec 2, abertura)
| Peça | Arquivo | Situação |
|---|---|---|
| ActionSchema automático (263 comandos, args tipados, aplicabilidade, efeitos, rótulos pt/en) | `nucleo/lang/esquema.py` | feito |
| IR independente de língua: `Ref` (node/selected/context/all/new), `Value` (SET/ADD/SUB/MUL/DIV), `Action` (com negação), `Plan` (sequência), `canonical` | `nucleo/lang/ir.py` | feito |
| Grounding por tipo de argumento; `Discourse` (estado discursivo); `Sandbox` (builder sem interface); `same_state` | `nucleo/lang/mundo.py` | feito; o estado discursivo ainda é fraco ("o mesmo") |
| Gerador hierárquico: evidência → operações → alvos → slots tipados → composição; ranqueador com traços cruzados; perceptron estruturado médio, ouro forçado só no TRAIN; famílias `lex`/`ev`/`struct`/`ctx` (para ablação) | `nucleo/lang/acoes_ranker.py` | feito; precisa de melhora |
| Evidência lexical com origem: catálogo, WordNet/ILI, índice de valores, Wiktionary, numerais | `nucleo/lang/evidencia.py` | feito |
| Auditoria automática de regras escondidas (perfilador + AST) | `experiments/a1/auditoria.py` | feito |
| Avaliação reproduzível: congelamento, vazamento, validação do ouro no builder, recall/ranking, IR/ação/estado, categorias, idiomas, holdout composicional, contrastes, diálogos, custo, ablações | `experiments/a1/avaliar.py` | feito |
| λ-cálculo tipado, CCG, UBL/FUBL, IBM1 (replicação GeoQuery: 593 de 597 derivações na época 1) | `nucleo/lang/ccg/` | base para a A2 |

## Corpus (congelado; hashes em `experiments/a1/congelado.json`)
| Conjunto | Itens |
|---|---|
| TRAIN | 167 |
| DEV | 60 |
| TEST | 189 (pt 98, en 91) |
| HOLDOUT composicional | 51 |
| CRUZADO | 4 |
| CONTRASTE | 11 pares |
| DIALOGOS | 8 |

**Categorias do TEST:** nova 45, sinônimo 39, combinação 34, contexto 32, flexão 19, pronome 16, ordem 11, sujeito 10,
elipse 10, negação 8, coordenação 8, composto 8, digitação 8.

**TEST, HOLDOUT, CRUZADO, CONTRASTE e DIALOGOS nunca foram medidos.** Isso é intencional: só rodam no portão.

## Números atuais: só DEV (`avaliar.py --dev`, log `data/cache/a1_dev.log`, 6 épocas, treino de 165 s)
| Métrica | Valor |
|---|---|
| cand@1 / @3 / @5 / **@10** / @todas | 75,0 / 81,7 / 81,7 / **86,7** / 91,7 |
| rank@1 / @3 / @5 | 76,7 / 81,7 / 81,7 |
| IR / ação / estado final corretos | 76,7 / 76,7 / 76,7 |

**Atenção, correção de leitura:** o critério da A1 é **recall@10 ≥ 95% no TEST** (`CRITERION_K = 10` em
`avaliar.py`). O DEV está em **86,7**, não em 91,7. O valor 91,7 é o recall sobre todas as candidatas, e foi o que a
sessão anterior citou ao usuário. Use sempre o @10.

## As 14 falhas do DEV e a categoria provável (spec 2 §14)
"fora" quer dizer que o ouro não foi gerado, ou seja, falha de **geração**. As demais são de **ranking**.

| # | Frase | Ouro → obtido | Categoria |
|---|---|---|---|
| 1 | deixa o título do painel em itálico | `ftit` font-style:italic → `tit` color:red | resolução de entidade (cadeia de genitivo) + propriedade/valor |
| 2 | alinha o título ao centro (fora) | text-align:center → color:red | geração / associação propriedade-valor |
| 3 | pinta o fundo do primeiro cartão de amarelo | `c1` → `c2` | resolução de entidade (ordinal) |
| 4 | aumenta a largura do botão em 30px | ADD → SUB | indução lexical (polaridade da operação relativa) |
| 5 | diminui a fonte do título em 2px (fora) | font-size → width | geração / propriedade |
| 6 | deixa o título azul e o rodapé cinza | blue → brown; color → text-decoration-color | propriedade/valor como unidade; ranking |
| 7 | faz o mesmo com o rodapé | toggleHidden → float:footnote | discurso/contexto (repetir a ação anterior) |
| 8 | deixa ele um pouco menor | DIV → MUL | indução lexical (polaridade) |
| 9 | esconde o primeiro cartão | o cartão → o título dentro dele | resolução de entidade (ordinal sobre o tipo nomeado) |
| 10 | add a paragraph at the end of the sidebar (fora) | element.insert → text-align:end | geração (inserção + posição) |
| 11 | make the headline blue and the footer gray | blue → azure; color → border-left-color | propriedade/valor; ranking |
| 12 | do the same to the footer | toggleHidden → font-weight | discurso/contexto |
| 13 | make it a bit smaller (fora) | DIV → valor "smaller" | geração (operação relativa) |
| 14 | hide the first card (fora) | o cartão → o título dele | resolução de entidade (ordinal) |

**Diagnóstico, não ordem.** Na leitura da passagem, as falhas se agrupam em cinco mecanismos. As sugestões abaixo
são hipóteses: o Codex decide o que atacar, em que ordem e como, e pode descartá-las. A única regra fixa é corrigir
no mecanismo, nunca por frase.
1. **Ordinais e cadeias de genitivo** (#1, #3, #9, #14): a referência deve escolher entre os irmãos do tipo nomeado
   ("cartão"), não entre os descendentes. Isso entra como traço estrutural aprendido sobre a relação entre o nó e o
   tipo nomeado, sem lista de palavras ordinais escrita à mão. A evidência de "primeiro" deve vir de recurso
   (numerais ou WordNet) ou do treino.
2. **Polaridade das operações relativas** (#4, #8, #13): ADD/SUB/MUL/DIV precisam competir na geração e ser
   decididos por traços aprendidos (palavra × operação de valor), além da evidência dos recursos. Verificar por que
   "aumenta" → SUB, apesar dos exemplos no TRAIN.
3. **Propriedade + valor como unidade** (#2, #5, #6, #11): spec 2 §8. O par (propriedade, valor) recebe evidência
   conjunta; uma cor nomeada deve preferir `color`/`background-color` pela evidência e pelo tipo do alvo, não por
   regra.
4. **"O mesmo" / "do the same"** (#7, #12): spec 2 §9. O `Discourse` precisa oferecer a ação anterior como
   candidata reaplicável a um novo alvo, e um traço `ctx` aprendido decide.
5. **Inserção com posição** (#10): a geração de `element.insert` com `parent`/`index` a partir de "at the end of".

## Marcos (a especificação define os critérios; o caminho entre eles é do Codex)
1. **Fechar a A1 no DEV.** Meta de trabalho: cand@10 ≥ 95% e rank@1 o mais alto possível. Medidas e commits vão no
   diário. A auditoria (`auditoria.py`) deve continuar sem regra manual.
2. **Portão da A1.** Uma execução completa de `avaliar.py`, uma vez só. Depois, escrever
   `docs/codex/relatorio_a1.md` com a tabela da spec 2 §17 (dataset, geração, ranking, generalização, idiomas,
   execução, integridade, hashes) e os números reais de `data/cache/a1_relatorio.json`.
   - **Passou** em todos os critérios da spec 2 §18: registre e siga para a A2.
   - **Falhou:** registre os números, a análise de erro por categoria e a causa, e decida o próximo caminho. Mudar
     de abordagem é permitido. Não ajuste nada olhando erros individuais do TEST. Um novo portão exige um conjunto
     de teste novo, congelado antes de ser medido.
3. **A2: parsing semântico completo.** Composição aprendida (CCG sobre a IR, com léxico induzido, usando
   `nucleo/lang/ccg/`): "aumente a margem esquerda do segundo botão" deve ser derivado composicionalmente, e a
   derivação deve ser uma variável latente aprendida pela execução (spec 1 §3, §4, §7).
4. **A3: contexto e diálogo** (spec 1 §5, spec 2 §9, §12).
5. **A4: execução e aprendizado integrado.**
   - `interpret.understand_request` passa a chamar o motor novo, mantendo a interface (`Understanding`, `Reading`,
     decisões `executar`/`perguntar`/...; veja o fim desta seção);
   - limiar calibrado para ≤ 0,5% de execução errada;
   - escolhas e desfazer viram exemplos de treino;
   - a web (porta 8790) passa a usar o motor novo;
   - os geradores, `COST`, `LIMIT`, `STATE_OF_FRAME` e `FRAME_COMMANDS` do motor antigo são removidos.

**Interface que a A4 precisa manter** (levantada na sessão anterior):
- `understand_request(text, world, by="usuario", lang=None) -> Understanding`;
- `Understanding(text, tokens, readings, decision, message, lang)` com `.best`;
- `Reading`:
  - `constraints` no formato `style/field/added/removed/moved/command/selected`;
  - `verb`, `frame`, `paraphrase`, `cost`, `ambiguous`, `unknown_verb`;
- `interpret._conversation_act(text)`, usado por `Assistant.handle`;
- os pontos para gravar exemplos são `Session._continue_dialogue` e `Assistant.undo`.

## O que já foi tentado e abandonado (não repita)
- **Rodadas e congelados escritos à mão, com uma regra por classe de erro** (`docs/plano_compreensao.md`, rodadas 7
  a 13, congelados v1 a v6). As medidas limpas nunca convergiram: 63 → 82 → 46 → 70 → 52 → 75%.
- **Geradores de leituras e custos escritos à mão** (`interpret.py`, `ground.py`, `base.COST`, `LIMIT`). No DocEdit,
  deram 8,6% certos.
- **Otimizar GeoQuery ou MATIS como objetivo.** O usuário proibiu: eles são só evidência.
