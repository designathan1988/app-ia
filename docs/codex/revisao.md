# Revisão (escrita pelo Claude, revisor; o Codex lê e aplica, mas não edita)

O veredito mais recente fica no topo. Correções marcadas **EXIGIDO** vêm antes de qualquer outro trabalho.

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
