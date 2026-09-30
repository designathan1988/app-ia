# Núcleo

Motor cognitivo **sem LLM** para programação. A inteligência vem de conhecimento
explícito, raciocínio com prova, busca, aprendizado estrutural e verificação.

- Plano aprovado: [docs/plano.md](docs/plano.md)
- Registro da pesquisa (90+ técnicas, com fontes): [docs/pesquisa.md](docs/pesquisa.md)
- Semântica formal com exemplos executáveis: [docs/semantica.md](docs/semantica.md)
- Achados (defeitos descobertos, com evidência): [docs/achados.md](docs/achados.md)

## Estado

**Regra:** nenhuma capacidade é listada aqui sem o teste que a comprova.

| Capacidade | Evidência | Estado |
|---|---|---|
| Linguagem de conhecimento: fatos, regras, negação forte, `not` sobre mundo fechado, `nao_consta` sobre mundo aberto, comparações | `tests/test_analysis.py`, `docs/semantica.md` | feito |
| Admissão: segurança, disciplina de mundo, estratificação com o ciclo exibido | `tests/test_analysis.py` | feito |
| Inferência em várias etapas, com recursão, sobre o modelo perfeito | diferencial contra oráculo ingênuo **e** clingo, 3.000 mundos aleatórios com nomes inventados (`scripts/ci.py`) | feito |
| Status epistêmico: VERDADEIRO / FALSO (afirmado, inferido, presumido, mundo_fechado), CONTRADITORIO, DESCONHECIDO | idem + 38 exemplos calculados à mão | feito |
| Prova de cada conclusão + checador independente (modelo estável: suporte + fechamento) | `tests/test_checker_adversarial.py`: provas e modelos corrompidos são rejeitados | feito |
| Invariância a nomes, à ordem e a conhecimento irrelevante | `tests/test_metamorphic.py` | feito |
| **Ponte sem interface com o builder-6:** store, comandos (256), predicados, manifesto e validador reais, rodando fora do navegador; recusas estruturadas; exportação HTML/CSS | `tests/test_builder_bridge.py`: 450 comandos reais aleatórios, todos os estados válidos pelo validador do próprio builder | feito (F0/X11) |
| Regras derrotáveis, agregados, contextos, versões, incremental, conjunto mínimo de conflito | — | próximo (M1) |

## Rodar

```
py -m venv C:\ctv\n
C:\ctv\n\Scripts\python.exe -m pip install pytest hypothesis clingo
C:\ctv\n\Scripts\python.exe scripts\ci.py
```
