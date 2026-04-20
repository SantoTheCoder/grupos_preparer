import asyncio
import json
import logging
import os
import re
import sys

from telethon import TelegramClient
from telethon.tl.functions.messages import EditChatDefaultBannedRightsRequest
from telethon.tl.types import ChatBannedRights
from telethon.errors import FloodWaitError, ChatNotModifiedError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings import BASE_DIR, config
from data.io_manager import PersistenceManager

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("DISABLE_MEDIA")

DRONE_SESSION_DIR = os.path.join(BASE_DIR, "user_client", "sessions")

async def main():
    persistence = PersistenceManager()
    groups = persistence.load_groups()
    
    if not groups:
        logger.error("Nenhum grupo encontrado em groups.json")
        return

    modifications = False
    
    # Restrição Absoluta de Midias
    banned_rights = ChatBannedRights(
        until_date=None,
        send_messages=False, # Pode mandar mensagem
        send_media=True,     # Bloqueado
        send_stickers=True,
        send_gifs=True,
        send_games=True,
        send_inline=True,
        embed_links=True,
        send_polls=True,
        change_info=True,
        invite_users=False,
        pin_messages=True,
        manage_topics=True,
        send_photos=True,
        send_videos=True,
        send_roundvideos=True,
        send_audios=True,
        send_voices=True,
        send_docs=True,
        send_plain=False
    )
    
    for index, record in enumerate(groups):
        node_name = record.get("node_operacional", "")
        match = re.search(r'bot_(\d+)', node_name)
        if not match:
            continue
            
        bot_number = int(match.group(1))
        
        # Filtro de execuçao
        if not (31 <= bot_number <= 65):
            continue
            
        if record.get("media_disabled") is True:
            logger.info("PULANDO: %s ja esta com as midias bloqueadas.", node_name)
            continue
            
        group_id = record.get("group_id")
        phone = record.get("phone")
        if not group_id or not phone:
            logger.error("Falta ID do grupo ou Telefone no %s.", node_name)
            continue
            
        logger.info("--------------------------------------------------")
        logger.info("Desativando midias no grupo do %s (%s)...", node_name, phone)
        session_path = os.path.join(DRONE_SESSION_DIR, f"{phone}.session")
        
        if not os.path.exists(session_path):
            logger.error("❌ Sessao ausente para %s.", node_name)
            continue
            
        client = TelegramClient(session_path, config.API_ID, config.API_HASH)
        
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.error("❌ Sessao do %s foi derrubada.", node_name)
                continue
                
            logger.info("Enviando comando EditChatDefaultBannedRightsRequest em %s...", group_id)
            try:
                entity = await client.get_entity(int(group_id))
                await client(EditChatDefaultBannedRightsRequest(peer=entity, banned_rights=banned_rights))
                
                logger.info("✅ SUCESSO! Midias bloqueadas no grupo %s", node_name)
                record["media_disabled"] = True
                groups[index] = record
                modifications = True
                persistence.save_groups(groups)
                
            except ChatNotModifiedError:
                logger.info("⚠️ O grupo %s JÁ estava com essas permissoes exatas. Marcando JSON.", node_name)
                record["media_disabled"] = True
                groups[index] = record
                modifications = True
                persistence.save_groups(groups)
            except Exception as e:
                logger.error("❌ Erro ao bloquear midias no %s: %s", node_name, e)
                    
        except FloodWaitError as e:
            logger.error("🛑 FloodWait no telefone %s. Aguarde %s seg.", phone, e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error("Erro critico na sessao do %s: %s", node_name, e)
        finally:
            await client.disconnect()
            
        await asyncio.sleep(2)

    logger.info("🏁 Operação de Bloqueio de Midias finalizada.")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
