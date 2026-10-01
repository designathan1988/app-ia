# Prompt inicial para o Codex

Abra uma conversa nova no Codex com a pasta **`C:\Codex-Shared\nucleo`** e cole o texto abaixo.

```
Você vai continuar a implementação da compreensão de linguagem natural (português e inglês) deste repositório, a partir do commit atual. Outra sessão (Claude) fez o trabalho até aqui e agora vai revisar o seu.

Antes de qualquer coisa, leia nesta ordem e siga à risca:
1. AGENTS.md (regras permanentes, ambiente, git, diário);
2. docs/codex/revisao.md (o retorno do revisor; aplique o que estiver marcado EXIGIDO primeiro);
3. docs/codex/especificacao.md (a minha especificação, na íntegra; ela governa tudo);
4. docs/codex/estado.md (onde parou, números, as 14 falhas do DEV e a próxima tarefa);
5. docs/codex/progresso.md (o diário; continue a partir da última entrada).

Tarefa: concluir a A1 e seguir para a A2, a A3 e a A4, sem reiniciar a arquitetura. Comece pelo item 1 de "Próxima tarefa" em estado.md: corrigir no DEV os cinco mecanismos de falha, um de cada vez, sempre no mecanismo responsável e nunca na frase. Depois, rode o portão da A1 uma única vez e escreva docs/codex/relatorio_a1.md com a tabela da especificação 2 §17.

Regras que não admitem exceção:
- nenhum LLM e nada neural;
- nenhum conhecimento linguístico em código: nem regex de intenção, nem if/switch por palavra, nem listas de paráfrases ou sinônimos, nem peso inicial escrito para uma palavra;
- não editar os conjuntos congelados e não usar --recongelar;
- o TEST roda só no portão;
- processos pesados em prioridade abaixo do normal, um por vez.

A cada passo concluído:
- faça um commit pequeno, com mensagem em inglês;
- rode git push origin main:master;
- acrescente uma entrada no topo de docs/codex/progresso.md, com o commit, o comando exato da medida e os números.

Não pare para perguntar nem para relatar à toa: continue até concluir a etapa. Pare só se um portão falhar (aí relate números, análise de erro por categoria e causa, sem remendo) ou se houver uma decisão que só eu possa tomar.
```

## Mensagens de continuação (depois de cada revisão)

Quando o revisor publicar um veredito novo em `docs/codex/revisao.md`, cole no Codex:

```
Há uma revisão nova em docs/codex/revisao.md. Leia; se apontar violação de regra ou de integridade, corrija; o resto é informação. Depois continue pelo caminho que você julgar melhor.
```
