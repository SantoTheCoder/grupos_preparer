# PIPELINE DE ORQUESTRAÇÃO ASSÍNCRONA (POA) - PREPARADOR DE GRUPOS

A arquitetura e percurso exato das necessidades para o Software, garantindo concorrência extrema e zero falsos estados:

## Fase 1: Setup Ambiental (Core)
- [ ] 1.1 Criar arquivo `.env` como repositório de constantes (`API_ID`, `API_HASH`, e credenciais do `BOT`).
- [ ] 1.2 Desenvolver integridade via `core/settings.py` (Tratamento seguro de variáveis numéricas/string).
- [ ] 1.3 Estabelecer ecossistema físico local na pasta `sessions/` para o Telethon não perder os Handshakes.

## Fase 2: User Client (Ingestão de Metadados)
- [ ] 2.1 Programar `user_client/app.py` integrando a Autenticação.
- [ ] 2.2 Módulo `user_client/extractor.py` varrendo assíncronamente os 30 grupos da conta alvo.
- [ ] 2.3 Consolidar mapeamentos em memória e injetar simultaneamente em JSON e CSV via `data/io_manager.py` (Matriz [Id Numérico x Link Único x Nome Antigo x Novo Nome]).

## Fase 3: User Client (Mutação Fria)
- [ ] 3.1 Script de inicialização (`user_client/mutator.py`).
- [ ] 3.2 **Esvaziamento Térmico**: Apagar TODO o histórico remanescente nos alvos de forma iterativa.
- [ ] 3.3 Setar "Nome Específico" novo no Chat.
- [ ] 3.4 Setar e salvar "Descrição Específica" no sobre o Chat.
- [ ] 3.5 Atualizar a interface injetando o bytearray atrelado à "Foto do Grupo".
- [ ] 3.6 Transacional primária: Enviar mensagem permanente e Fixar (Pin) instantaneamente.
- [ ] 3.7 Atribuir poderes de Admin/Moderador isolados ao nosso Bot Cliente nos 30 grupos.

## Fase 4: Bot Client (Delegação e Limpeza Operacional)
- [ ] 4.1 Estruturar a inicialização reativa via `bot_client/app.py` (usando orquestrador *Aiogram* ou versão limpa similar).
- [ ] 4.2 Middleware de Purgação Atômica: Interceptar e apagar mensagens do sistema de eventos do Telegram (Membro Entrou, Saiu, Mensagem Fixada, Remoção de Avatares) a 0.04ms.
- [ ] 4.3 Scheduler Baseado em Loop (`bot_client/scheduler.py`): Injetar a lógica cronometrada do "Banner Diário", enfileirando sem obstrução e protegendo de limites HTTP `429 Too Many Requests`.

## Fase 5: Controlador Central
- [ ] 5.1 Encapsular lógicas em um `main.py` CLI limpo (Roteamento entre rodar _"Extrator/Preparador"_ ou executar o _"Bot em Watchdog"_).
