import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from telethon import TelegramClient
from telethon.tl.types import ChatBannedRights
from telethon.tl.functions.messages import EditChatDefaultBannedRightsRequest
from telethon.errors.rpcerrorlist import FloodWaitError

from core.settings import config, SESSION_DIR, DATA_DIR, BASE_DIR
from data.io_manager import PersistenceManager

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("UNLOCK_CHAT")

async def main():
    persistence = PersistenceManager()
    master_session = os.path.join(SESSION_DIR, 'user_account.session')
    master = TelegramClient(master_session, config.API_ID, config.API_HASH, flood_sleep_threshold=0)

    await master.connect()
    if not await master.is_user_authorized():
        logger.error("Mestre nao autorizado.")
        return

    accounts_map = persistence.load_accounts()
    groups = persistence.load_groups()

    total = 0
    success = 0
    failed = 0

    for acc in accounts_map:
        person = acc.get("name", "Desconhecido")
        account_id = acc.get("account_id")
        phone = acc.get("phone")
        owned_groups = [
            g
            for g in groups
            if g.get("account_id") == account_id or (g.get("owner") == person and g.get("phone") == phone)
        ]

        if not owned_groups:
            continue

        session_path = os.path.join(BASE_DIR, 'user_client', 'sessions', f"{phone}.session")
        if not os.path.exists(session_path):
            logger.warning(f"Sessao ausente para {phone}. Skip.")
            continue

        worker = TelegramClient(session_path, acc.get('api_id', config.API_ID), acc.get('api_hash', config.API_HASH), flood_sleep_threshold=0)
        await worker.connect()

        if not await worker.is_user_authorized():
            logger.warning(f"Drone [{person}] deslogado. Skip.")
            await worker.disconnect()
            continue

        dialogs = await worker.get_dialogs(limit=100)
        dialog_map = {d.id: d.entity for d in dialogs}

        for g in owned_groups:
            g_code = g.get("internal_code", "")
            g_id = g.get("group_id")
            entity = dialog_map.get(g_id)

            if not entity:
                logger.warning(f"Grupo [{g_code}] nao encontrado para [{person}]. Skip.")
                failed += 1
                continue

            total += 1
            logger.info(f"-> [{person}] >> [{getattr(entity, 'title', g_code)}] (ID:{g_id})")

            try:
                # EditChatDefaultBannedRightsRequest(peer, default_banned_rights) — positional
                # False = permitido, True = bloqueado
                await worker(EditChatDefaultBannedRightsRequest(
                    entity,
                    ChatBannedRights(
                        until_date=None,
                        send_messages=False,   # ✅ Permitido
                        send_media=True,       # ❌ Bloqueado
                        send_stickers=True,    # ❌ Bloqueado
                        send_gifs=True,        # ❌ Bloqueado
                        send_games=True,       # ❌ Bloqueado
                        send_inline=True,      # ❌ Bloqueado
                        embed_links=True,      # ❌ Bloqueado
                        invite_users=False,    # ✅ Permitido (add members)
                        pin_messages=True,     # ❌ Bloqueado
                        change_info=True       # ❌ Bloqueado
                    )
                ))
                logger.info(f"   ✅ Chat aberto.")
                success += 1
            except FloodWaitError as e:
                logger.warning(f"   ⏳ Flood: aguardando {e.seconds}s...")
                await asyncio.sleep(e.seconds)
                failed += 1
            except Exception as e:
                logger.error(f"   ❌ Erro: {e}")
                failed += 1

            await asyncio.sleep(2)

        await worker.disconnect()

    await master.disconnect()
    logger.info(f"\nFIM: {total} processados | {success} abertos | {failed} falharam")

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
