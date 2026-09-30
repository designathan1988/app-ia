# Semântica formal do núcleo de conhecimento (M1)

Este documento define **o que é verdade** para o motor. Todo exemplo marcado com
`%?` é executado pelo teste `tests/test_semantics_examples.py` contra:
- o motor;
- o oráculo ingênuo;
- o clingo;
- o checador independente.

As expectativas foram calculadas à mão a partir das definições abaixo, antes da execução.

## 1. Linguagem

- **Termos:** variáveis (maiúscula ou `_`), símbolos (minúscula), inteiros, textos entre aspas.
  - A ordem total é inteiros < símbolos < textos.
  - Inteiros comparam numericamente; símbolos e textos, lexicograficamente.
- **Átomos:** `p(t1,…,tn)` e a **negação forte** `-p(t1,…,tn)`. Formalmente, `-p` é um predicado distinto de `p`.
- **Literais de corpo:**
  - positivos: `p(…)` ou `-p(…)`;
  - `not q(…)`, a negação por falha, **só para `q` de mundo fechado**;
  - `nao_consta(q(…))`, a ausência sobre qualquer predicado, que marca a conclusão como suposição;
  - comparações `= != < <= > >=`.
- **Declarações:** `pred nome/aridade fechado|aberto.` O padrão é `aberto`. `-p` herda o mundo de `p`.

## 2. Admissão (programas rejeitados antes de rodar)

1. **Segurança:** toda variável da cabeça, de `not`/`nao_consta` e de comparações aparece num literal positivo do corpo.
2. `not q` exige `q` fechado. Ausência sobre predicado aberto se escreve `nao_consta`.
3. **Fechamento do mundo fechado:** a regra de um predicado fechado só usa predicados fechados e não usa `nao_consta`. Assim, a ausência de um fato fechado significa falsidade.
4. **Estratificação:** nenhum ciclo de dependência passa por `not`/`nao_consta`. A mensagem de rejeição mostra o ciclo.

## 3. Modelo

**Definição.**
- O programa admitido tem um único **modelo perfeito** M: o menor modelo, calculado estrato por estrato.
- Os átomos `p` e `-p` são tratados como independentes.
- `not a` e `nao_consta(a)` são verdadeiros em M quando `a ∉ M`.
- M coincide com o único modelo estável do programa. É isso que o checador verifica: suporte bem-fundado + fechamento.

**Custo de prova.**
- Todo átomo de M tem uma prova de custo mínimo `(t, s)` em ordem lexicográfica.
- `t = 1` se a prova usa `nao_consta` em algum passo, `0` caso contrário.
- `s` é o número de passos.
- Consequência: se existe uma prova sem suposição, ela é a escolhida.

## 4. Status epistêmico de um átomo positivo fechado `p(c)`

| `p(c)` ∈ M | `-p(c)` ∈ M | status |
|---|---|---|
| sim | sim | **CONTRADITORIO** (duas provas) |
| sim | não | **VERDADEIRO** — `afirmado` se é fato; `inferido` se a melhor prova tem t=0; `presumido` se t=1 |
| não | sim | **FALSO** — mesmos qualificadores, pela prova de `-p(c)` |
| não | não, `p` fechado | **FALSO(mundo_fechado)** |
| não | não, `p` aberto | **DESCONHECIDO** |

**Paraconsistência.** Uma contradição não contamina conclusões que não dependem dela, e regras continuam a disparar a partir de premissas contraditórias (§5, ex. 13–14 e 39).

## 5. Exemplos (executados pelo teste)

Cada bloco é um programa independente. Linhas `%? átomo => STATUS` ou `%? átomo => STATUS(qualificador)` são as expectativas.

### Fatos e mundos

```nl
% 1. fato em mundo aberto
p(a).
%? p(a) => VERDADEIRO(afirmado)
%? p(b) => DESCONHECIDO
```

```nl
% 2. mundo fechado
pred p/1 fechado.
p(a). q(b).
%? p(b) => FALSO(mundo_fechado)
```

```nl
% 3. negação forte afirmada
-p(a).
%? p(a) => FALSO(afirmado)
%? p(b) => DESCONHECIDO
```

```nl
% 4. contradição afirmada
p(a). -p(a).
%? p(a) => CONTRADITORIO
```

```nl
% 30. fechado com negação explícita: o explícito prevalece sobre o mundo fechado
pred p/1 fechado.
-p(a). q(b).
%? p(a) => FALSO(afirmado)
%? p(b) => FALSO(mundo_fechado)
```

```nl
% 31. fechado com fato e negação: contradição
pred p/1 fechado.
p(a). -p(a).
%? p(a) => CONTRADITORIO
```

### Regras e inferência em várias etapas

```nl
% 5. regra simples
q(X) :- p(X).
p(a).
%? q(a) => VERDADEIRO(inferido)
%? q(b) => DESCONHECIDO
```

```nl
% 6. fecho transitivo, profundidade 4
pred pai/2 fechado. pred anc/2 fechado.
pai(a, b). pai(b, c). pai(c, d). pai(d, e).
anc(X, Y) :- pai(X, Y).
anc(X, Z) :- pai(X, Y), anc(Y, Z).
%? anc(a, e) => VERDADEIRO(inferido)
%? anc(e, a) => FALSO(mundo_fechado)
%? anc(b, a) => FALSO(mundo_fechado)
```

```nl
% 7. recursão sobre grafo com ciclo termina
pred e/2 fechado. pred r/2 fechado.
e(a, b). e(b, c). e(c, a).
r(X, Y) :- e(X, Y).
r(X, Z) :- r(X, Y), e(Y, Z).
%? r(a, a) => VERDADEIRO(inferido)
%? r(c, b) => VERDADEIRO(inferido)
```

```nl
% 33. cadeia longa (profundidade 10)
pred s/2 fechado. pred ate/2 fechado.
s(n0, n1). s(n1, n2). s(n2, n3). s(n3, n4). s(n4, n5).
s(n5, n6). s(n6, n7). s(n7, n8). s(n8, n9). s(n9, n10).
ate(X, Y) :- s(X, Y).
ate(X, Z) :- s(X, Y), ate(Y, Z).
%? ate(n0, n10) => VERDADEIRO(inferido)
%? ate(n10, n0) => FALSO(mundo_fechado)
```

```nl
% 34. recursão mútua (par/ímpar) sobre sucessor fechado
pred suc/2 fechado. pred par/1 fechado. pred impar/1 fechado.
suc(0, 1). suc(1, 2). suc(2, 3). suc(3, 4).
par(0).
impar(X) :- suc(Y, X), par(Y).
par(X) :- suc(Y, X), impar(Y).
%? par(4) => VERDADEIRO(inferido)
%? impar(3) => VERDADEIRO(inferido)
%? par(3) => FALSO(mundo_fechado)
%? par(0) => VERDADEIRO(afirmado)
```

```nl
% 35. losango: várias derivações, um só status
pred e/2 fechado. pred r/2 fechado.
e(a, b). e(a, c). e(b, d). e(c, d).
r(X, Y) :- e(X, Y).
r(X, Z) :- e(X, Y), r(Y, Z).
%? r(a, d) => VERDADEIRO(inferido)
%? r(d, a) => FALSO(mundo_fechado)
```

```nl
% 24. fato também derivável: afirmado prevalece
p(a).
p(X) :- q(X).
q(a).
%? p(a) => VERDADEIRO(afirmado)
```

```nl
% 26. junção com desigualdade
pred pai/2 fechado. pred irmao/2 fechado.
pai(p, x). pai(p, y). pai(q, z).
irmao(X, Y) :- pai(P, X), pai(P, Y), X != Y.
%? irmao(x, y) => VERDADEIRO(inferido)
%? irmao(x, x) => FALSO(mundo_fechado)
%? irmao(x, z) => FALSO(mundo_fechado)
```

```nl
% 27. variável anônima
pred pai/2 fechado. pred tem_filho/1 fechado.
pai(p, x).
tem_filho(X) :- pai(X, _).
%? tem_filho(p) => VERDADEIRO(inferido)
%? tem_filho(x) => FALSO(mundo_fechado)
```

```nl
% 18. predicados sem argumentos
chove.
molhado :- chove.
%? molhado => VERDADEIRO(inferido)
%? chove => VERDADEIRO(afirmado)
```

```nl
% 19. fechado derivado de fechado
pred a/1 fechado. pred b/1 fechado.
a(k).
b(X) :- a(X).
%? b(k) => VERDADEIRO(inferido)
%? b(z) => FALSO(mundo_fechado)
q(z).
```

### Negação por falha (mundo fechado) e ausência (mundo aberto)

```nl
% 8. órfão: negação por falha sobre predicado fechado
pred pessoa/1 fechado. pred tem_pai/1 fechado. pred pai/2 fechado. pred orfao/1 fechado.
pessoa(ana). pessoa(bia). pai(ana, bia).
tem_pai(X) :- pai(Y, X).
orfao(X) :- pessoa(X), not tem_pai(X).
%? orfao(ana) => VERDADEIRO(inferido)
%? orfao(bia) => FALSO(mundo_fechado)
```

```nl
% 32. negação sobre relação fechada vazia
pred n/1 fechado. pred bloqueado/1 fechado. pred livre/1 fechado.
n(a). n(b).
livre(X) :- n(X), not bloqueado(X).
%? livre(a) => VERDADEIRO(inferido)
%? livre(b) => VERDADEIRO(inferido)
```

```nl
% 20. negação sobre predicado fechado derivado (estratos)
pred n/1 fechado. pred e/2 fechado. pred alc/1 fechado. pred inalc/1 fechado.
n(a). n(b). n(c). e(a, b).
alc(a).
alc(Y) :- alc(X), e(X, Y).
inalc(X) :- n(X), not alc(X).
%? inalc(c) => VERDADEIRO(inferido)
%? inalc(b) => FALSO(mundo_fechado)
```

```nl
% 9. suposição sobre mundo aberto vira PRESUMIDO
talvez(X) :- p(X), nao_consta(q(X)).
p(a).
%? talvez(a) => VERDADEIRO(presumido)
```

```nl
% 11. a suposição cai quando o conhecimento aparece
talvez(X) :- p(X), nao_consta(q(X)).
p(a). q(a).
%? talvez(a) => DESCONHECIDO
```

```nl
% 10. prova limpa prevalece sobre prova com suposição
r(X) :- p(X), nao_consta(q(X)).
r(X) :- p(X), s(X).
p(a). s(a).
%? r(a) => VERDADEIRO(inferido)
```

```nl
% 22. PRESUMIDO se propaga
talvez(X) :- p(X), nao_consta(q(X)).
s(X) :- talvez(X).
p(a).
%? s(a) => VERDADEIRO(presumido)
```

```nl
% 23. FALSO presumido
-p(X) :- r(X), nao_consta(q(X)).
r(a).
%? p(a) => FALSO(presumido)
```

```nl
% 40. nao_consta sobre predicado aberto derivado
d(X) :- b(X).
e(X) :- a(X), nao_consta(d(X)).
a(k). a(m). b(m).
%? e(k) => VERDADEIRO(presumido)
%? e(m) => DESCONHECIDO
```

### Negação forte, contradição e paraconsistência

```nl
% 21. negação forte derivada
-p(X) :- q(X).
q(a).
%? p(a) => FALSO(inferido)
```

```nl
% 12. Tweety sem regras derrotáveis: a contradição fica localizada
ave(X) :- pinguim(X).
voa(X) :- ave(X).
-voa(X) :- pinguim(X).
pinguim(tweety). ave(piu).
%? voa(tweety) => CONTRADITORIO
%? voa(piu) => VERDADEIRO(inferido)
```

```nl
% 28. contradição derivada pelos dois lados
p(X) :- a(X).
-p(X) :- b(X).
a(k). b(k). a(m).
%? p(k) => CONTRADITORIO
%? p(m) => VERDADEIRO(inferido)
```

```nl
% 13. paraconsistência: a contradição não contamina o que não depende dela
p(a). -p(a). q(b).
%? q(b) => VERDADEIRO(afirmado)
%? q(a) => DESCONHECIDO
```

```nl
% 14. regras disparam a partir de premissa contraditória
p(a). -p(a).
r(X) :- p(X).
%? r(a) => VERDADEIRO(inferido)
```

```nl
% 39. contradição se propaga pelos dois lados de forma controlada
p(a). -p(a).
q(X) :- p(X).
-q(X) :- -p(X).
%? q(a) => CONTRADITORIO
```

```nl
% 29. desconhecido quando nada se sabe
q(b).
%? p(a) => DESCONHECIDO
```

### Comparações e termos

```nl
% 15. comparação numérica
pred idade/2 fechado. pred mais_velho/2 fechado.
idade(ana, 30). idade(bia, 25).
mais_velho(X, Y) :- idade(X, A), idade(Y, B), A > B.
%? mais_velho(ana, bia) => VERDADEIRO(inferido)
%? mais_velho(bia, ana) => FALSO(mundo_fechado)
```

```nl
% 16. ordem total: inteiros < símbolos, símbolos por ordem alfabética
pred v/1 fechado. pred menor/1 fechado.
v(3). v(abd). v(abb).
menor(X) :- v(X), X < abc.
%? menor(3) => VERDADEIRO(inferido)
%? menor(abb) => VERDADEIRO(inferido)
%? menor(abd) => FALSO(mundo_fechado)
```

```nl
% 17. textos
nome(ana, "Ana Maria").
tem_nome(X) :- nome(X, N), N != "".
%? tem_nome(ana) => VERDADEIRO(inferido)
%? nome(ana, "Ana Maria") => VERDADEIRO(afirmado)
```

```nl
% 37. igualdade com constante
pred cor/2 fechado. pred azul/1 fechado.
cor(b1, azul). cor(b2, verde).
azul(X) :- cor(X, C), C = azul.
%? azul(b1) => VERDADEIRO(inferido)
%? azul(b2) => FALSO(mundo_fechado)
```

```nl
% 38. inteiros negativos
pred temp/2 fechado. pred frio/1 fechado.
temp(poa, -3). temp(rio, 28).
frio(X) :- temp(X, T), T < 0.
%? frio(poa) => VERDADEIRO(inferido)
%? frio(rio) => FALSO(mundo_fechado)
```

## 6. Limites desta versão (M1, primeira fatia)

**Ainda não implementado:**
- regras derrotáveis e o status INDETERMINADO;
- agregados;
- contextos e versões;
- manutenção incremental;
- conjunto mínimo de conflito;
- regras aprendidas (HIPOTÉTICO).

**Limite do checador:** ele verifica a *existência* das provas, mas não a
*minimalidade*. O qualificador `presumido` ("não existe prova limpa") é
verificado pelo oráculo nos testes diferenciais, não pelo checador.
