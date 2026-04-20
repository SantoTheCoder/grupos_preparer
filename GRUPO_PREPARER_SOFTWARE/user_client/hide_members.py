import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.functions.channels import ToggleParticipantsHiddenRequest
from telethon.errors import FloodWaitError, ChatNotModifiedError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings import BASE_DIR, config
from data.io_manager import PersistenceManager

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("HIDE_MEMBERS")

DRONE_SESSION_DIR = os.path.join(BASE_DIR, "user_client", "sessions")

async def main():
    persistence = PersistenceManager()
    groups = persistence.load_groups()
    
    if not groups:
        logger.error("Nenhum grupo encontrado em groups.json")
        return

    modifications = False
    
    for index, record in enumerate(groups):
        node_name = record.get("node_operacional", "")
        match = re.search(r'bot_(\d+)', node_name)
        if not match:
            continue
            
        bot_number = int(match.group(1))
        
        # Filtro de execuçao (os 35 grupos criados)
        if not (31 <= bot_number <= 65):
            continue
            
        if record.get("hidden_members") is True:
            logger.info("PULANDO: O grupo do %s ja teve a lista de membros oculta.", node_name)
            continue
            
        group_id = record.get("group_id")
        phone = record.get("phone")
        if not group_id or not phone:
            logger.error("Falta ID do grupo ou Telefone no %s.", node_name)
            continue
            
        logger.info("--------------------------------------------------")
        logger.info("Iniciando sessao do drone %s (%s) para esconder membros...", node_name, phone)
        session_path = os.path.join(DRONE_SESSION_DIR, f"{phone}.session")
        
        if not os.path.exists(session_path):
            logger.error("❌ Sessao ausente para %s: %s", node_name, session_path)
            continue
            
        client = TelegramClient(session_path, config.API_ID, config.API_HASH)
        
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.error("❌ Sessao do drone %s (%s) foi derrubada/deslogada.", node_name, phone)
                continue
                
            logger.info("Enviando comando ToggleParticipantsHiddenRequest em %s...", group_id)
            try:
                entity = await client.get_entity(int(group_id))
                await client(ToggleParticipantsHiddenRequest(channel=entity, enabled=True))
                
                logger.info("✅ SUCESSO! Lista de membros oculta no grupo %s", node_name)
                record["hidden_members"] = True
                groups[index] = record
                modifications = True
                persistence.save_groups(groups)
                
            except ChatNotModifiedError:
                logger.info("⚠️ O grupo %s JÁ estava com os membros ocultos. Marcando JSON.", node_name)
                record["hidden_members"] = True
                groups[index] = record
                modifications = True
                persistence.save_groups(groups)
            except Exception as e:
                error_msg = str(e).lower()
                if "chattoosmall" in error_msg or "chat_too_small" in error_msg or "chat too small" in error_msg:
                    logger.warning("⚠️ Grupo do %s não tem 100 membros ainda. Membros da API JAP estão a caminho. Tentaremos mais tarde.", node_name)
                else:
                    logger.error("❌ Erro ao ocultar membros no %s: %s", node_name, e)
                    
        except FloodWaitError as e:
            logger.error("🛑 FloodWait no telefone %s. Aguarde %s seg.", phone, e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error("Erro critico na sessao do %s: %s", node_name, e)
        finally:
            await client.disconnect()
            
        # Atraso termico para evitar ban no telethon
        await asyncio.sleep(2)

    logger.info("🏁 Operação de Ocultação finalizada.")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
