import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import logging
from telethon import TelegramClient

from core.settings import config, SESSION_DIR, BASE_DIR
from bot_agent.modules.cleaner import get_cleaner_handler

# Motor de Observabilidade Absoluta (Tracing Bot)
log_file = os.path.join(BASE_DIR, 'debug_bot.log')
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ZELADOR.Core")

async def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "seu_bot_token_aqui":
        logger.error("🛑 CRÍTICO: Você não configurou a chave BOT_TOKEN no seu arquivo .env!")
        return

    session_file = os.path.join(SESSION_DIR, 'bot_account.session')
    # O bot não precisa de injeção de DeviceModel super complexa, mas usamos telethon standard
    client = TelegramClient(session_file, config.API_ID, config.API_HASH)
    
    logger.info("🔌 Ignitando Baterias Principais...")
    await client.start(bot_token=config.BOT_TOKEN)
    logger.info("🟢 [SYSTEM ONLINE] - Agente Zelador Acordou no Servidor.")
    
    # 1. Acopla o Scanner (Event Listener de Deleção)
    bot_info = await client.get_me()
    logger.info(f"   -> Identidade Assumida: @{bot_info.username}")
    
    client.add_event_handler(get_cleaner_handler())
    logger.info("   -> Protocolo Scanner: LIGADO (Filtro Anti-Serviço Ativo)")

    # Trava o Main Loop (Fica rodando até o processo ser morto no CMD)
    logger.info("🧊 Kernel trancado em O(1). O bot está rodando e persistindo no background infinitamente...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    # Força renderização do UTF-8 estrito no CMD Windows
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("❌ SINAL SIGINT: Bot desligado na base.")
