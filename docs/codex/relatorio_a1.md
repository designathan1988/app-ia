# Relatório A1 — portão de 2026-10-01

**Veredito: REPROVADO.** O gerador recuperou o ouro no Top-10 em **127/189 exemplos (67,2%)** do TEST. O mínimo é 95% (180/189 neste conjunto). O DEV havia atingido 95,0%; esse resultado não generalizou para o TEST.

## Execução e condições

- Motor: commit `408f676`; avaliador/auditoria: `1a150a4`; HEAD no início: `34bbb84`.
- Python: `C:/ctv/n/Scripts/python.exe`, Python 3.12, modelos lineares/estatísticos locais; 6 épocas, TRAIN com 167 exemplos.
- Início registrado: `2026-10-01T17:07:42.0545616-03:00`. Duração reportada: **1.886 s** (31 min 26 s). Prioridade BelowNormal; um trabalho pesado por vez.
- Treino: **301 updates**, 59 early updates; 166/167 exemplos com ouro naturalmente gerado na última época. São os mesmos contadores da última medida DEV.
- Uma única execução completa, com ablações previstas. Nenhum ajuste no motor foi feito após os resultados do TEST.
- Builder observado: `5fa86206da29bc9dd027dd2c54d327103ad2d62a`, commit anterior ao início da avaliação; não foi alterado por este trabalho.

Comando da avaliação (precedido da checagem local de que o portão ainda não tinha iniciado):

```powershell
(Get-Process -Id $PID).PriorityClass = 'BelowNormal'
$env:PYTHONIOENCODING = 'utf-8'
C:/ctv/n/Scripts/python.exe experiments/a1/avaliar.py | Tee-Object -FilePath data/cache/a1_portao.log
```

Fontes: `data/cache/a1_relatorio.json`, `data/cache/a1_portao.log` e `data/cache/a1_auditoria.json`. O relatório JSON e os logs permanecem no cache, fora do Git. As tabelas abaixo são transcritas desse resultado; a linha agregada das ablações soma os indicadores já gravados, sem nova inferência.

## Conjuntos

| Conjunto | n |
|---|---:|
| TRAIN | 167 |
| DEV | 60 |
| TEST | 189 |
| HOLDOUT | 51 |
| CRUZADO | 4 |
| CONTRASTE (11 pares) | 22 |
| DIALOGOS (8 diálogos, turnos) | 30 |

TEST: 98 exemplos PT e 91 EN. Os conjuntos e seus hashes permaneceram congelados.

## Geração de candidatas

Percentuais de enunciados cujo ouro está naturalmente no conjunto indicado. **O critério é cand@10; cand@todas não o substitui.**

| Conjunto | n | cand@1 | cand@3 | cand@5 | cand@10 | cand@todas |
|---|---:|---:|---:|---:|---:|---:|
| DEV | 60 | 81,7 | 91,7 | 93,3 | 95,0 | 98,3 |
| TEST | 189 | 46,6 | 58,2 | 63,0 | 67,2 | 89,9 |
| HOLDOUT | 51 | 54,9 | 66,7 | 72,5 | 76,5 | 88,2 |
| CRUZADO | 4 | 100,0 | 100,0 | 100,0 | 100,0 | 100,0 |
| CONTRASTE | 22 | 54,5 | 68,2 | 68,2 | 68,2 | 100,0 |

## Ranking e execução

| Conjunto | n | rank@1 | rank@3 | rank@5 | IR | Ação grounded | Estado final |
|---|---:|---:|---:|---:|---:|---:|---:|
| DEV | 60 | 81,7 | 91,7 | 93,3 | 81,7 | 81,7 | 81,7 |
| TEST | 189 | 50,3 | 62,4 | 67,2 | 49,2 | 49,7 | 50,8 |
| HOLDOUT | 51 | 56,9 | 70,6 | 72,5 | 58,8 | 58,8 | 58,8 |
| CRUZADO | 4 | 100,0 | 100,0 | 100,0 | 100,0 | 100,0 | 100,0 |
| CONTRASTE | 22 | 54,5 | 68,2 | 68,2 | 54,5 | 54,5 | 63,6 |

A métrica IR existente compara as ações canônicas como multiconjunto; não verifica, sozinha, a ordem da sequência. Para planos com várias ações, o avaliador usa `max(K, número de ações-ouro)` no Top-K. A comparação de dispatches preserva a ordem e o estado final é obtido executando o plano no builder. Esses limites fazem parte da interpretação dos números, sem alterar o protocolo depois de olhar o TEST.

## Generalização e idiomas no TEST

As categorias se sobrepõem. “Lexical unseen” e “inflection unseen” automáticos usam, respectivamente, lemas de conteúdo ausentes do TRAIN e formas novas de lemas já vistos; a categoria congelada “flexão” tem definição e população diferentes.

| Categoria | n | cand@1 | cand@3 | cand@5 | cand@10 | rank@1 | rank@3 | rank@5 | IR | Ação | Estado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Vocabulário não visto (automático) | 97 | 32,0 | 40,2 | 43,3 | 47,4 | 35,1 | 47,4 | 49,5 | 35,1 | 35,1 | 37,1 |
| Flexão não vista (automático) | 9 | 66,7 | 88,9 | 88,9 | 88,9 | 66,7 | 88,9 | 88,9 | 66,7 | 66,7 | 66,7 |
| Formulação nova | 45 | 26,7 | 40,0 | 46,7 | 46,7 | 26,7 | 42,2 | 48,9 | 26,7 | 26,7 | 26,7 |
| Sinônimo / paráfrase rotulada | 39 | 30,8 | 41,0 | 43,6 | 48,7 | 41,0 | 51,3 | 53,8 | 41,0 | 41,0 | 46,2 |
| Flexão (categoria congelada) | 19 | 42,1 | 57,9 | 57,9 | 63,2 | 42,1 | 73,7 | 73,7 | 42,1 | 42,1 | 42,1 |
| Ordem das palavras | 11 | 90,9 | 100,0 | 100,0 | 100,0 | 100,0 | 100,0 | 100,0 | 100,0 | 100,0 | 100,0 |
| Combinação nova | 34 | 82,4 | 91,2 | 94,1 | 97,1 | 82,4 | 91,2 | 94,1 | 82,4 | 85,3 | 85,3 |
| Contexto | 32 | 50,0 | 59,4 | 62,5 | 65,6 | 56,2 | 62,5 | 62,5 | 56,2 | 56,2 | 56,2 |
| Pronome | 16 | 62,5 | 81,2 | 81,2 | 87,5 | 62,5 | 81,2 | 81,2 | 62,5 | 62,5 | 62,5 |
| Elipse | 10 | 0,0 | 0,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 | 10,0 |
| Negação | 8 | 50,0 | 62,5 | 62,5 | 62,5 | 50,0 | 62,5 | 62,5 | 50,0 | 50,0 | 50,0 |
| Coordenação | 8 | 25,0 | 62,5 | 75,0 | 87,5 | 25,0 | 62,5 | 75,0 | 0,0 | 0,0 | 0,0 |
| Comando composto | 8 | 0,0 | 25,0 | 75,0 | 87,5 | 0,0 | 25,0 | 75,0 | 0,0 | 0,0 | 0,0 |
| Digitação | 8 | 25,0 | 37,5 | 37,5 | 50,0 | 25,0 | 37,5 | 50,0 | 25,0 | 25,0 | 25,0 |
| Sujeito omitido | 10 | 80,0 | 100,0 | 100,0 | 100,0 | 90,0 | 100,0 | 100,0 | 90,0 | 90,0 | 90,0 |
| Português | 98 | 45,9 | 60,2 | 63,3 | 68,4 | 50,0 | 64,3 | 68,4 | 49,0 | 50,0 | 51,0 |
| Inglês | 91 | 47,3 | 56,0 | 62,6 | 65,9 | 50,5 | 60,4 | 65,9 | 49,5 | 49,5 | 50,5 |

O HOLDOUT contém 51 exemplos: a checagem encontrou ao menos uma combinação ausente do TRAIN em todos eles. Seu cand@10 foi 76,5% e seu estado final correto, 58,8%. Portanto a generalização composicional exigida ainda não está demonstrada em nível suficiente.

## Equivalência e diálogos

- Pares PT/EN agregados por mesma página, contexto e ouro: **10**; mesma IR prevista **30,0%**; mesma IR e correta **10,0%**.
- CRUZADO tem somente **4 exemplos**, todos corretos; esse conjunto pequeno não substitui a medida agregada de equivalência.
- CONTRASTE: ambos os lados corretos em **36,4% dos 11 pares**.

| Histórico dos diálogos | Turnos | cand@10 | rank@1 | IR | Ação | Estado |
|---|---:|---:|---:|---:|---:|---:|
| Histórico correto fornecido | 30 | 50,0 | 43,3 | 43,3 | 43,3 | 46,7 |
| Histórico previsto pelo sistema | 30 | 46,7 | 36,7 | 36,7 | 36,7 | 40,0 |

## Ablações

Mesma população: **TEST + HOLDOUT, n=240**. As variantes são as pré-definidas no avaliador, treinadas somente em TRAIN.

| Variante | cand@10 | rank@1 | rank@3 | rank@5 | IR | Ação | Estado |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sistema completo | 69,2 | 51,7 | 64,2 | 68,3 | 51,2 | 51,7 | 52,5 |
| sem contexto | 65,8 | 46,2 | 56,7 | 61,7 | 45,0 | 45,0 | 45,8 |
| sem evidencia externa | 74,6 | 41,7 | 59,2 | 70,0 | 40,0 | 40,0 | 40,0 |
| sem tracos estruturais | 75,4 | 48,8 | 62,9 | 70,8 | 47,5 | 47,5 | 49,2 |
| sem aprendizado | 10,4 | 3,3 | 5,8 | 6,2 | 3,3 | 3,3 | 5,8 |

O aprendizado produz grande ganho sobre a inicialização; o efeito das demais famílias não é uniforme. Retirar evidência externa ou traços estruturais aumenta cand@10 neste conjunto, mas reduz rank@1. Isso não autoriza escolher outra variante depois do TEST e apresentar o mesmo conjunto como validação limpa.

Limite das ablações: os rótulos correspondem às famílias de features implementadas, não à remoção formal de toda informação relacionada. Por exemplo, desligar `ctx` não elimina o traço estrutural `x-op-ref`; desligar `struct` não elimina todos os traços de dependência/caso. Esses números não isolam completamente contexto ou sintaxe.

## Custo

| Item | Medida |
|---|---:|
| Comandos no manifesto do builder | 263 |
| ActionSchemas elegíveis no motor | 144 |
| Candidatas médias por enunciado (conjuntos avaliados) | 418,2 |
| Candidatas p50 / p95 / máximo | 373 / 713 / 1.687 |

A contagem de 263 comandos vem de `len(load_commands())`; 144 vem de `len(schemas())`, que filtra operações elegíveis. Não são o mesmo universo.

**Latência real de inferência, sem perfilador:** DEV, n=60, recursos aquecidos. Inclui análise linguística, geração, ranking e decodificação; exclui preparação de documento/discurso e execução no builder.

| Componente | Média (ms) | p95 (ms) |
|---|---:|---:|
| Inferência completa | 93,856 | 201,641 |
| Geração | 81,723 | 185,791 |
| Ranking | 9,394 | 22,363 |

Os tempos da execução instrumentada ficaram separados no JSON (`cost.profiling_enabled=true`): geração 261,0/630,8 ms e ranking 28,7/59,8 ms (média/p95). **Não são apresentados como latência de produção.** Não houve experimento de aumento artificial do catálogo; a contagem de candidatas observada não prova escalabilidade para catálogos maiores.

## Integridade

| Checagem | Resultado |
|---|---|
| Sobreposição exata TRAIN/TEST | 0 |
| Sobreposição normalizada / acentos / reorder / quase duplicatas detectadas | 0 / 0 / 0 / 0 |
| Gold inválido na validação de corpus | 0 |
| Gold usado para gerar candidatas TEST | 0 — geração recebe texto, idioma, página e discurso; comparação vem depois |
| Regras de intenção / regex de intenção / pesos iniciais por palavra | 0 / 0 / 0 na auditoria final |
| Conhecimento legado com efeito | 0 na auditoria; entidades legadas filtradas antes do limite |
| Regras manuais de paráfrase detectadas no caminho auditado | 0; não há prova formal para código não exercitado |
| Cobertura da auditoria | TRAIN, DEV, TEST, HOLDOUT, CRUZADO, CONTRASTE, diálogos e ablações |
| Chamadas completas de geração observadas / funções do projeto | 5.384 / 271 |
| TEST antes do portão / repetição da avaliação completa | 0 / 0 nesta sessão |

Os checks de vazamento detectam identidade, normalização, acentos, reorder e Jaccard ≥0,8; não provam ausência de toda paráfrase derivada de uma mesma ideia/seed. Não existem identificadores de seed que permitam uma auditoria completa dessa origem.

A medida foi executada sem alterar os conjuntos. O teste de determinismo compara pesos exatos, índice e estatísticas em duas sementes e após preflight TRAIN+DEV. O treino do portão repetiu os 301/59 updates observados no DEV. A origem dos 180 updates históricos da passagem não foi demonstrada e não é atribuída ao preflight sem evidência.

## Análise de erro por mecanismo

- **Candidate generation:** 19/189 exemplos não tiveram todo o ouro gerado. Em outros 43 o ouro foi gerado, mas ficou fora do Top-10. São as 62 falhas do critério principal.
- **Ranking:** 96 exemplos tiveram IR incorreta; em 77 deles o ouro estava entre as candidatas. Recuperar o ouro em algum ponto da lista não basta.
- **Lexical induction / morphology:** o subconjunto automático de vocabulário não visto tem cand@10 47,4% e rank@1 35,1% (n=97). A recuperação e o ranking de evidências novas são fracos. Os dados agregados não separam completamente ausência lexical, erro de análise morfológica e poda.
- **Syntax/composition:** nos 16 exemplos de coordenação ou comandos compostos, todas as ações-ouro foram geradas, mas nenhuma IR/plano final ficou correta. O gerador segmenta a entrada, enquanto o treino forçado usa a frase inteira e a deduplicação pode perder a derivação do segmento; são limitações de mecanismo identificadas antes do portão.
- **Discourse/context:** nas 10 elipses, o ouro foi gerado em todas, mas cand@10 e IR ficaram em 10,0%. No diálogo end-to-end, o estado correto ficou em 40,0%. A existência do candidato de repetição não garante que a continuidade seja aprendida ou preservada.
- **Entity resolution / property/value association:** os diagnósticos prévios do DEV mostraram ordinais sem ligação ao tipo mencionado e transferência indevida de valores entre propriedades. Os agregados do TEST não permitem quantificar isoladamente cada causa sem uma investigação adicional; não foi feita nova inferência no TEST.
- **Schema limitation / grounding:** a leitura anterior ao portão encontrou geração de argumentos extras, nomes de slots ignorados e texto usado para argumentos JSON. Exemplos de capacidades afetadas são `style.reset`, `style.setTransform` e slots nomeados de `element.swapDirection`. Isso limita a validade das hipóteses e não foi corrigido a partir de erros individuais do TEST.
- **Execution:** entre os casos com ação grounded correta, não houve estado final incorreto no TEST. A principal falha observada está antes da execução: recuperação, escolha e composição da interpretação.

**Conclusão causal:** o ganho de consistência corrigiu um defeito real do aprendizado, mas o sistema ainda não generaliza suficientemente vocabulário, composição e continuidade. A A1 não passa; não houve retreinamento corretivo nem nova rodada do TEST após esse diagnóstico.

## Hashes congelados

| Conjunto | SHA-256 |
|---|---|
| TRAIN | `86233e2ae5214691853064918602ffdaf29c0c7bb77358f04026e2cb72537a06` |
| DEV | `2d1bcea910357441250eb777559c0c6deba021a2881d45a54c50218bdda78aaf` |
| TEST | `4b192a42517a87118788ec6dfdde16035792fb6872343e38eb39edd503866f02` |
| HOLDOUT | `2d4ec5b1c70baef513d01287676d74a98f3d3436192b70a438a2d43831f73cb0` |
| CRUZADO | `40e8cfb41a2c2510f8e7012d025c9374bc04aaf3dcf8335e8e3126fa63044bab` |
| CONTRASTE | `c2eba4718b9d0fb43881fb657f961069b3f5bfcd2e760f80ee86db621265ee30` |
| DIALOGOS | `788302979f90598a4d08e242594e1839b5e31a986b5e9f3394cde27d93f99b38` |

Hashes dos artefatos desta execução:

- `a1_relatorio.json`: `34af3cd7a8496d277c0e537499ea8a10553127efeabfe0c778e8093f58b45d05`
- `a1_portao.log`: `86ab22001b3910502d419654a6cd34bcbadb52429fa4a07987f9560b47664371`

## Estado após o portão

A1 reprovada. A web continua usando o motor antigo; este resultado não autoriza dizer que o usuário pode testar o motor novo. A medida externa DocEdit/MASSIVE ainda não foi executada para este motor. Pela instrução definitiva posterior do usuário, a reprovação não encerra a missão: o diagnóstico orientará dados novos e generalização lexical/composicional, preservando este teste consumido e sem ajustar novamente ao DEV A1. A próxima comprovação usará um teste novo congelado e as medidas externas exigidas.
