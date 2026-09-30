# Experimentos

Cada experimento responde a uma pergunta que decide o desenho. As respostas são **medidas**, com o script que as
reproduz.

## X1 — A gramática aberta do português serve de base para entender pedidos de programação?

**Texto de teste, que não é meu:** o catálogo pt-BR do builder-6 (`src/i18n/locales/pt-BR.json` e `glossary.json`),
escrito pelos autores do builder. São os rótulos de comandos, da paleta, dos elementos e das propriedades: 616 rótulos
e 1.549 palavras.

### X1a — Morfologia exata a partir de dados abertos (`experiments/x1_lexico.py`)

**Fontes:**
- MorphoBr (Apache-2.0) para palavras de classe aberta;
- palavras funcionais **observadas** nos treebanks UD (Porttinari, PetroGold, Bosque), com as contrações vindas dos
  tokens compostos do UD (`às` = a + as);
- compostos com hífen analisados pelas partes.

**Nenhuma lista de palavras foi digitada.**

| Medida | Valor |
|---|---|
| Tipos (palavras distintas) analisados | **429 / 441 = 97,3%** |
| Ocorrências analisadas | **98,1%** |
| Não analisadas | `all canvas css gap html padding svg tag translate url zip` (estrangeirismos, que o glossário do builder define como conceitos) e `mesclagem` (derivação ausente no MorphoBr) |

### X1b — Análise sintática com a gramática GF do português (`experiments/x1_gf.py`)

**O que foi usado:**
- A gramática de recursos GF do português "segue majoritariamente o português brasileiro" (README do gf-rgl).
- O léxico é **gerado** a partir do X1a.
- Cada rótulo é analisado como enunciado (`Utt`).
- **Proteções do medidor:**
  - só contam árvores sintáticas reais;
  - uma frase-controle precisa ser analisada;
  - qualquer erro de compilação aborta a medição.
  - Uma primeira versão sem essas proteções reportou um **falso 100%** quando a gramática não compilava. O defeito foi
    corrigido antes de qualquer conclusão.

| Configuração | Cobertura | Ambiguidade mediana (máx.) | Tempo (584 rótulos) |
|---|---|---|---|
| Léxico por paradigmas "inteligentes" do GF | 489/584 = 83,7% | 3 (249) | 87 s |
| **Léxico com todas as formas exatas do MorphoBr** | **523/584 = 89,6%** | 3 (280) | 40–47 s |

**Achados sobre a gramática aberta:**
1. **Os paradigmas automáticos de flexão do GF para o português erram:**
   - `inferior` gera o feminino "inferiora";
   - `aplicar` é conjugado como "apficar / apfico / apfiquei".

   Decisão: **a IA nunca adivinha flexão**. Toda forma vem do MorphoBr, com a tabela verbal completa de 63 formas.
2. **A coordenação de infinitivos** ("mostrar ou ocultar", "adicionar ou remover") está declarada no módulo
   `Extend` mas **não implementada** para as línguas românicas (`MkVPI` e `ConjVPI` = `variants {}` em
   `ExtendRomanceFunctor.gf`). É uma construção geral da língua a implementar por nós.
3. **Falhas restantes, por padrão:**
   - siglas e estrangeirismos (`SVG`, `URL`, `ID`, `X`/`Y`, `padding`);
   - compostos no léxico da gramática (`quadro-chave`, `pré-visualização`);
   - contração com demonstrativo (`desta`);
   - substantivo + substantivo ("tamanho base");
   - particípio como adjetivo ("texto transbordado");
   - nome sem artigo depois de preposição ("com retângulo");
   - predicativo com "como" ("salvar os estilos como classe").
4. **Ambiguidade:** a mediana de 3 análises por rótulo é administrável; a cauda chega a 280. Escolher entre as análises
   é papel da interpretação por abdução contra o manifesto (plano, §1). A gramática sozinha não decide.

**Conclusão do X1 (viabilidade):** **sim**. Sem escrever nenhuma regra de domínio, a gramática aberta + morfologia exata
analisam ~90% da linguagem humana do builder. As falhas têm causas identificadas e são todas construções *gerais* do
português (coordenação, siglas, compostos, aposição), não vocabulário de domínio.

**Custo:**
- a gramática compilada ocupa 4,3 MB;
- a morfologia vem dos dados do MorphoBr (623 MB brutos; o índice compacto ainda está por medir);
- as ~40 s por 584 frases (~70 ms por frase) incluem compilar a gramática a cada execução.

### X1c — Ativar as construções do `Extend` sem restrição (resultado negativo)

Ativamos `CompoundN`, `PastPartAP` e `ApposNP` do módulo `Extend` sobre a gramática inteira:

| Medida | Valor |
|---|---|
| Memória do GF | **mais de 21 GB** (processo interrompido por nós para proteger a máquina) |
| Ambiguidade máxima | **~9 milhões de análises** para um único rótulo |
| Cobertura até a interrupção | 57% (a medição não chegou ao fim) |

**Causa:** `CompoundN : N -> N -> N` é recursiva. Sobre um léxico de 800 entradas, sequências de substantivos geram um
número exponencial de árvores.

**Decisões:**
1. Compostos entram **pelo léxico** (compostos observados, como `quadro-chave`), não por uma regra recursiva geral.
2. Toda análise roda com **teto de resultados** e **ordenação por pesos** aprendidos por contagem (a gramática
   probabilística do plano), nunca enumerando tudo.
3. Todo experimento com gramática roda com um **limite de memória e de tempo**, vigiado pelo harness.

**Próximo passo:**
- implementar a coordenação de infinitivos (ausente no GF românico);
- tratar siglas e estrangeirismos como nomes do léxico;
- aplicar as construções do `Extend` de forma restrita e medir de novo.
