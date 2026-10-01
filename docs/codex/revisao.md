# Revisão (escrita pelo Claude, revisor; o Codex lê e aplica, mas não edita)

O veredito mais recente fica no topo. Correções marcadas **EXIGIDO** vêm antes de qualquer outro trabalho.

---

## Revisão 3 (2026-10-01, 16:20): ritmo e próxima fase
**Veredito:** o trabalho está correto, mas **lento demais**. Há 25 minutos não há commit, e o ganho já medido
(consistência: cand@10 de 86,7 para 95,0) continua fora da árvore.

**O que vi:**
- Determinismo resolvido na causa:
  - empates ordenados em `concepts.meanings`, na evidência, nas âncoras e em `slot_ev`;
  - duas execuções do DEV idênticas;
  - `test_a1_determinism.py` passando.
- Nada commitado ainda: `concepts.py`, `evidencia.py`, `acoes_ranker.py` e o teste estão só na árvore.
- Integridade ok: conjuntos congelados intactos, TEST intocado, nenhuma regra nova.

**EXIGIDO, nesta ordem e sem desvio:**
1. **Agora:** commit e push do determinismo, com o teste. Não espere a medida em curso.
2. Aplique a consistência treino/inferência, meça o DEV uma vez, faça commit e push.
3. **Prazo para o DEV: 2 horas** depois do item 2.
   - Ataque só mecanismos que passem no critério de aceite.
   - Ao fim do prazo, vá ao **portão da A1** de qualquer jeito.
   - Escreva `relatorio_a1.md` com os números reais, passando ou não.
4. **Depois do portão, se passar:**
   - **Medida em frases escritas por outras pessoas**, uma vez: DocEdit dev (en, tipo de ação, roteiro O3) e
     MASSIVE dev pt/en (execuções erradas, O4), com adaptador para o motor novo. É regra permanente do usuário que
     a medida principal use conjuntos externos. O corpus A1 foi escrito pelo mesmo autor do TRAIN e **não prova**
     compreensão da língua de outras pessoas.
   - **Ligação experimental na web**, para o usuário poder testar:
     - `understand_request` usa o motor novo, mantendo a interface;
     - executa só acima de um limiar calibrado no DEV;
     - abaixo dele, pergunta mostrando as 2 ou 3 melhores leituras;
     - a escolha do usuário vira exemplo de treino (A4 adiantada; o resto da A2 e da A3 continua depois);
     - o motor antigo fica atrás de uma opção, para comparação.

     Só então diga ao usuário que ele pode testar, explicando o que funciona e o que não funciona.

---

## Revisão 2 (2026-10-01, 16:15): aplicação da Revisão 1 em andamento, sem commit novo
**Veredito:** no caminho certo. O achado mais importante até agora ainda não foi commitado.

**O que vi:**
- **Reprodutibilidade, em curso e bem feita:**
  - `tests/test_a1_determinism.py` treina duas vezes, com `PYTHONHASHSEED` 1 e 2, e compara pesos e índice
    invertido;
  - também testa a soma de pontuação e o corte da evidência do grafo, independentemente da ordem;
  - `a1_dev_repro_before_1.log` é idêntico a `a1_dev_before.log` (173 updates, a mesma tabela). A segunda execução
    estava rodando.
  - A diferença contra `1960f1c` (180 updates) parece vir do preflight antigo, que executava o ouro reservado antes
    do treino. **Isso precisa ser confirmado e escrito no diário**, porque significa que o treino dependia de estado
    deixado por outra execução, por exemplo caches ou o sandbox.
- **Consistência treino/inferência** (`a1_consistency.patch`, guardado fora da árvore até a repetibilidade estar
  provada, o que está correto). A medida DEV de `a1_dev_consistency.log`:

  | Métrica | Antes | Depois |
  |---|---|---|
  | cand@10 | 86,7 | **95,0** |
  | rank@1 | 75,0 | **81,7** |
  | IR | 75,0 | 81,7 |

  É uma correção de mecanismo (o traço genérico de ação que faltava na geração), não de frase. Aceita pelo
  critério da Revisão 1.

**EXIGIDO (além dos itens pendentes da Revisão 1):**
1. Faça o commit da consistência **depois** do teste de determinismo passar, refaça a medida DEV com o patch
   aplicado e registre antes e depois.
2. **Não persiga 100% no DEV.**
   - São 60 frases, 1 frase vale 1,7 ponto, e o DEV já foi muito inspecionado.
   - Ataque os mecanismos que ainda falham (ordinais, "o mesmo", polaridade e propriedade+valor) só se cada um
     passar no critério de aceite.
   - Depois, vá ao **portão** (avaliação completa, uma vez), com a auditoria `--portao` pronta.
   - O DEV a 95 não garante o TEST: o TEST tem 39 frases de sinônimo e 34 de combinação nova. Quem decide é o
     portão.

---

## Revisão 1 (2026-10-01, ~16:10): commits `b378dee`, `2eeab16` e `450eb29`, mais o trabalho não commitado
**Veredito:** o método está **satisfatório**; o resultado **ainda não apareceu**. Nos ~30 min desde a passagem, o
cand@10 do DEV continua em 86,7.

**O que está certo:**
- Os conjuntos congelados estão intactos: nenhum diff em `congelado.json` nem em
  treino/dev/teste/holdout/contrastes/dialogos.
- O TEST não foi medido.
- Isolar o `--dev` do ouro reservado (`preflight`) estava correto e veio com teste.
- A correção da prioridade de CPU foi verificada por teste em processo filho.
- Honestidade: as tentativas de referências (`a1_dev_references*.log`) não foram commitadas.
  - A v1 caiu para cand@10 85,0 e rank@1 71,7.
  - A v2 subiu o cand@10 para 88,3, mas derrubou o rank@1 para 68,3.
  - A queda do rank@1 de 76,7 para 75,0 foi registrada sem inventar causa.
- O desalinhamento entre os traços do treino forçado e os da inferência (`featurize` contra `generate`), ainda não
  commitado, é um defeito real de mecanismo, e o teste sintético com tokens abstratos é a forma certa de prová-lo.
- Nenhuma regra linguística nova. `ACTING`/`CONTENT` e `{"ADJ", "NUM"}` são categorias UPOS, ou seja, estruturais.
  Os traços `*-bound-rank` são lexicalizados pela palavra observada e aprendidos, não enumerados.

**EXIGIDO, nesta ordem:**
1. **Reprodutibilidade antes de qualquer comparação.**
   - O código de treino não mudou entre `1960f1c` e `b378dee`, e mesmo assim o treino mudou: 180 contra 173
     updates, 72 contra 67 early updates, rank@1 76,7 contra 75,0.
   - Ou o treino não é determinístico (ordem de iteração de `set`/`frozenset` de strings, que varia com o
     `PYTHONHASHSEED`, ou de caches), ou depende do que o `preflight` executa antes, por exemplo caches aquecidos
     por outros conjuntos.
   - No DEV, 1 frase vale 1,7 ponto. Enquanto isso não estiver resolvido, nenhuma diferença dessa ordem é
     interpretável.
   - **Faça:**
     - rode o `--dev` duas vezes no mesmo commit e compare `updates` e a tabela;
     - encontre a fonte da variação e torne a ordem determinística **no código** (iteração ordenada), não só fixando
       a semente;
     - acrescente um teste: dois treinos curtos sobre um subconjunto do TRAIN geram os mesmos pesos;
     - registre no diário.
2. **Commitar a correção de consistência treino/inferência** isoladamente, com o teste
   `tests/test_a1_feature_consistency.py` e a medida DEV antes e depois, já com o item 1 resolvido.
3. **Critério de aceitação de cada mecanismo:**
   - **cand@10 sobe e rank@1 não cai** mais de 1 frase sem explicação demonstrada;
   - uma mudança como a references_v2 (+1,6 de cand@10, −6,7 de rank@1) não entra como está.

   O ranking também é parte da A1: a spec 2, §17, exige Top-1, 3 e 5.
4. **Auditoria no portão.** Em desenvolvimento, auditar só TRAIN+DEV está certo. No portão, porém, a
   `auditoria.py` precisa percorrer **todos** os conjuntos (por exemplo `--portao`), porque um caminho de código
   exercitado só pelo TEST escaparia da auditoria. Implementar agora e usar só no portão.
5. Menor: em `progresso.md`, mantenha o parágrafo "Formato no AGENTS.md §7..." logo abaixo do título, com as entradas
   depois dele.

**Na próxima revisão vou checar:**
- determinismo comprovado: duas execuções iguais;
- commits por mecanismo, com cand@10 e rank@1 antes e depois;
- `congelado.json` intacto;
- TEST intocado;
- nenhuma regra nova.

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
