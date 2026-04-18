# Plano de Implementacao

## Objetivo

- Reorganizar o fluxo para que o `drone` crie e administre o grupo do zero.
- Deixar o `master` apenas para a etapa final.
- Adicionar os bots `@FiscalDoGrupoBot` e `@IaDetetive_Bot` ao fluxo.

## Papeis

### Drone

- Cria o grupo do zero.
- Fixa o grupo na lista de conversas do proprio drone, no topo dos chats fixados.
- Define nome, descricao e foto.
- Adiciona o `master` como contato.
- Garante que o `master` tambem tenha o `drone` como contato.
- Adiciona o `master` no grupo.
- Da admin ao `master`.
- Adiciona `@FiscalDoGrupoBot` no grupo.
- Da admin ao `@FiscalDoGrupoBot`.
- Adiciona `@IaDetetive_Bot` no grupo.
- Da admin ao `@IaDetetive_Bot`.
- Extrai e salva `nome + id + link` do grupo.

### Master

- Entra no grupo ja pronto.
- Posta a mensagem fixada (`foto + texto`) uma unica vez.
- Fixa a mensagem.
- Cria o gift.
- Resgata/dispara o gift no grupo.

### Bot

- `@FiscalDoGrupoBot`.
- Entra no final do fluxo.
- Recebe admin.
- Permanece apenas como bot operacional do grupo, sem postagem recorrente automatica.

### Bot de Gift

- `@IaDetetive_Bot`.
- E adicionado pelo `drone` antes da etapa final do `master`.
- Recebe admin para conseguir detectar e resgatar o gift no grupo.

## Mudancas principais

- Remover do `master` toda responsabilidade de administrar grupos.
- Remover a ideia de grupo orfao.
- Fazer o grupo nascer sempre pela conta `drone`.
- Salvar sempre os dados finais do grupo:
  - `nome`
  - `id`
  - `link`
  - `owner/drone`

## Implementacao

1. Ajustar o modelo de dados para ter uma fila de grupos a criar com nome real e dono real.
2. Ajustar o fluxo de autenticacao para trabalhar com `master` e `drones`.
3. Reescrever o orquestrador principal para:
   - usar o `drone` como criador do grupo;
   - adicionar contato mutuo entre `drone` e `master`;
   - adicionar `master` no grupo e dar admin;
   - adicionar `@FiscalDoGrupoBot` no grupo e dar admin;
   - adicionar `@IaDetetive_Bot` no grupo e dar admin;
   - extrair `nome + id + link` apos a criacao.
4. Integrar a etapa final do `master`:
   - postar `foto + texto`;
   - fixar;
   - gerar e resgatar gift.
5. Atualizar os JSONs finais com os dados reais do grupo.
6. Manter o bot no final sem rotina de postagem recorrente.

## Arquivos que devem mudar

- `user_client/mutator.py`
- `user_client/gift_injector.py`
- `data/io_manager.py`
- `user_client/auth_manager.py`
- `core/settings.py`
- `bot_agent/*`

## Resultado esperado

- Cada grupo e criado pelo seu `drone`.
- O `master` entra apenas na etapa final.
- O `master` sempre consegue ser adicionado porque havera vinculo mutuo de contato.
- O `@FiscalDoGrupoBot` entra no fluxo final ja com admin.
- O `@IaDetetive_Bot` entra antes da etapa de gift ja com admin.
- O sistema termina com os grupos organizados em JSON com `nome + id + link`.
