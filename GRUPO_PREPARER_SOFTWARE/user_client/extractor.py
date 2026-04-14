import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import telethon.network.mtprotostate
telethon.network.mtprotostate.MSG_TOO_OLD_DELTA = 999999999
telethon.network.mtprotostate.MSG_TOO_NEW_DELTA = 999999999

import logging
import asyncio
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.errors import FloodWaitError
from core.settings import config, SESSION_DIR
from data.io_manager import PersistenceManager

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class GroupExtractor:
    """Motor de Ingestão de Telethon. Mapeia a infraestrutura sem mutabilidade destrutiva (-O(1))."""
    def __init__(self):
        # Sessão física alocada de forma estrita em disco próprio para evitar lock do EventLoop
        session_file = os.path.join(SESSION_DIR, 'user_account.session')
        self.client = TelegramClient(session_file, config.API_ID, config.API_HASH)
        self.persistence = PersistenceManager()

    async def extract_groups(self):
        """Varre descritores TCP do usuário extraindo correlações matriciais (ID x Nome)."""
        await self.client.start(phone=config.PHONE)
        logger.info("🔌 [CONEXÃO MTPROTO] Handshake inicial sincronizado.")

        groups_data = []
        
        async for dialog in self.client.iter_dialogs():
            entity = dialog.entity
            
            # Filtro térmico: Apenas Chats regulares e Supergrupos. Exclui broadcasts (Canais de aviso).
            is_group = False
            if isinstance(entity, Chat):
                is_group = True
            elif isinstance(entity, Channel) and getattr(entity, 'megagroup', False):
                is_group = True

            if is_group:
                group_id = dialog.id
                group_name = dialog.name
                invite_link = "N/A"

                try:
                    # Recupera link via roteamento (Username primário ou geração de Hash efêmera)
                    if hasattr(entity, 'username') and entity.username:
                        invite_link = f"https://t.me/{entity.username}"
                    else:
                        full_chat = await self.client(ExportChatInviteRequest(peer=entity))
                        invite_link = full_chat.link
                except FloodWaitError as e:
                    logger.warning(f"⚠️ [API RATE LIMIT] Telegram invocou suspensão térmica. Dormindo {e.seconds}s...")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.debug(f"ℹ️ Bloqueio lógico na extração do convite ({group_id}): {e}")

                logger.info(f"🟢 Alvo fixado: {group_name} | [{group_id}]")
                
                groups_data.append({
                    "id": group_id,
                    "old_name": group_name,
                    "new_name": "", # Reservado para a Matriz de Mutação
                    "link": invite_link
                })
                
                # Jitter induzido para mitigar colisões da camada HTTP do Telegram
                await asyncio.sleep(0.8)

        self.persistence.save_state(groups_data)
        logger.info(f"✅ Ingestão estrutural encerrada. Carga total: {len(groups_data)} matrizes consolidadas.")
        await self.client.disconnect()


if __name__ == "__main__":
    extractor = GroupExtractor()
    asyncio.run(extractor.extract_groups())
