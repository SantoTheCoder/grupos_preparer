import sys
import os
import re
import json
import random
import logging
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from telethon import TelegramClient
from telethon.tl.types import Chat, Channel, ChatAdminRights
from telethon.tl.functions.channels import EditAdminRequest, EditTitleRequest, EditPhotoRequest as ChannelEditPhotoRequest
from telethon.tl.functions.messages import EditChatAboutRequest, EditChatTitleRequest, EditChatPhotoRequest
from telethon.errors import FloodWaitError
from core.settings import config, SESSION_DIR, BASE_DIR, DATA_DIR
from data.io_manager import PersistenceManager
import argparse

import telethon.network.mtprotostate
telethon.network.mtprotostate.MSG_TOO_OLD_DELTA = 999999999
telethon.network.mtprotostate.MSG_TOO_NEW_DELTA = 999999999

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_file = os.path.join(BASE_DIR, 'debug_mutator.log')
logging.basicConfig(level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(log_file, encoding='utf-8', mode='a'), logging.StreamHandler(sys.stdout)])
logging.getLogger('telethon').setLevel(logging.INFO)
logger = logging.getLogger("ORQUESTRA_MESTRE")

class FleetOrchestrator:
    def __init__(self):
        support_session = os.path.join(SESSION_DIR, 'user_account.session')
        self.support_client = TelegramClient(support_session, config.API_ID, config.API_HASH, 
                                             device_model="Desktop Windows", flood_sleep_threshold=0)
        self.persistence = PersistenceManager()
        
        self.accounts_map = []
        mapping_path = os.path.join(DATA_DIR, 'accounts_mapping.json')
        if os.path.exists(mapping_path):
            with open(mapping_path, 'r', encoding='utf-8') as f:
                self.accounts_map = json.load(f)

    def _extract_code(self, name):
        replacements = {'𝗔':'A', '𝗕':'B', '𝗖':'C', '𝗗':'D', '𝗘':'E', '𝗙':'F', '𝗚':'G', '𝗛':'H', '𝗜':'I',
                        '𝟬':'0', '𝟭':'1', '𝟮':'2', '𝟯':'3', '𝟰':'4', '𝟱':'5', '𝟲':'6', '𝟳':'7', '𝟴':'8', '𝟵':'9'}
        clean_name = name
        for k, v in replacements.items():
            clean_name = clean_name.replace(k, v)
        
        match = re.search(r'#([A-Z0-9]{2,3})', clean_name)
        if match:
            return match.group(1)
        return clean_name

    def get_owner_for_group(self, new_name):
        code = self._extract_code(new_name)
        for acc in self.accounts_map:
            for g in acc.get("groups", []):
                if g == code or g in new_name or g in code:
                    return acc
        return None

    async def _execute_mutations(self, client, entity_id, new_name, uploaded_photo, bot_entity_str):
        try:
            # FIX ABSOLUTO: Formata o ID do canal para o Telethon reconhecer como Megagroup (prefixo -100)
            proper_id = entity_id
            if not str(entity_id).startswith('-100'):
                proper_id = int(f"-100{entity_id}")

            try:
                entity = await client.get_entity(proper_id)
            except Exception:
                await client.get_dialogs(limit=50) # Popula o cache
                try:
                    entity = await client.get_entity(proper_id)
                except Exception as e:
                    logger.error(f"Erro fatal: Sua conta NÃO ESTÁ NESTE GRUPO ou o cache falhou: {e}")
                    return entity_id, False, 0
                    
            if hasattr(entity, 'migrated_to') and entity.migrated_to is not None:
                entity = await client.get_entity(entity.migrated_to)
                
            entity_id = entity.id

            logger.info("   -> [1/4] Varredura de histórico...")
            async for msg in client.iter_messages(entity_id, limit=30):
                await msg.delete()

            logger.info("   -> [2/4] Modificando MetaDados Fisicos (Tít/Desc/Foto)...")
            with open(os.path.join(DATA_DIR, 'group_description.txt'), 'r', encoding='utf-8') as f:
                new_about = f.read()

            rights = ChatAdminRights(change_info=True, post_messages=True, edit_messages=True, delete_messages=True, ban_users=True, invite_users=True, pin_messages=True, add_admins=False, anonymous=False, manage_call=True)

            if isinstance(entity, Channel):
                try: await client(EditTitleRequest(channel=entity, title=new_name))
                except FloodWaitError as e: raise e
                except Exception: pass
                
                try: await client(EditChatAboutRequest(peer=entity, about=new_about))
                except FloodWaitError as e: raise e
                except Exception: pass
                
                if uploaded_photo:
                    try: await client(ChannelEditPhotoRequest(channel=entity, photo=uploaded_photo))
                    except FloodWaitError as e: raise e
                    except Exception: pass
                
                try: await client(EditAdminRequest(channel=entity, user_id=bot_entity_str, admin_rights=rights, rank="Vigia"))
                except FloodWaitError as e: raise e
                except Exception: pass
            else:
                try: await client(EditChatTitleRequest(chat_id=entity_id, title=new_name))
                except FloodWaitError as e: raise e
                except Exception: pass
                
                try: await client(EditChatAboutRequest(peer=entity_id, about=new_about))
                except FloodWaitError as e: raise e
                except Exception: pass
                
                if uploaded_photo:
                    try: await client(EditChatPhotoRequest(chat_id=entity_id, photo=uploaded_photo))
                    except FloodWaitError as e: raise e
                    except Exception: pass
                    
            return entity_id, True, 0
        except FloodWaitError as e:
            logger.warning(f"⏳ FLOODWAIT: Aguardará {e.seconds}s.")
            return entity_id, False, e.seconds
        except Exception as e:
            logger.error(f"Erro na conta: {e}")
            return entity_id, False, 0

    async def run_fleet(self):
        await self.support_client.start(phone=config.PHONE)
        logger.info("👑 CÉREBRO: Conexão MAESTRO estabelecida.")

        groups = self.persistence.load_state()
        if not groups: return

        sup_uploaded_photo = None
        if os.path.exists(config.AVATAR_PATH):
            sup_uploaded_photo = await self.support_client.upload_file(config.AVATAR_PATH)

        retry_queue = []
        max_flood_time = 0

        for group in groups:
            entity_id = group["id"]
            new_name = group.get("new_name", "").strip()
            
            if group.get("status") == "MUTADO":
                continue
            if not new_name:
                continue

            owner = self.get_owner_for_group(new_name)
            final_entity_id = entity_id
            mutation_success = True

            if owner:
                logger.info(f"👥 [DELEGAÇÃO] [{new_name}] pertence a: {owner['name']}. Drone local...")
                session_path = os.path.join(BASE_DIR, 'user_client', 'sessions', f"{owner['phone']}.session")
                
                if os.path.exists(session_path):
                    worker = TelegramClient(session_path, owner['api_id'], owner['api_hash'], flood_sleep_threshold=0)
                    await worker.connect()
                    if await worker.is_user_authorized():
                        worker_photo = await worker.upload_file(config.AVATAR_PATH) if os.path.exists(config.AVATAR_PATH) else None
                        bot_entity_str = config.BOT_USERNAME
                        
                        final_entity_id, success, flood_seconds = await self._execute_mutations(worker, entity_id, new_name, worker_photo, bot_entity_str)
                        if not success:
                            mutation_success = False
                            max_flood_time = max(max_flood_time, flood_seconds)
                    else:
                        logger.warning(f"⚠️ Conta {owner['name']} deslogada! Suporte cobrindo.")
                        final_entity_id, success, flood_seconds = await self._execute_mutations(self.support_client, entity_id, new_name, sup_uploaded_photo, config.BOT_USERNAME)
                        if not success:
                            mutation_success = False
                            max_flood_time = max(max_flood_time, flood_seconds)
                    await worker.disconnect()
                else:
                    logger.warning(f"⚠️ Sessão {owner['name']} não encontrada. Suporte cobrindo.")
                    final_entity_id, success, flood_seconds = await self._execute_mutations(self.support_client, entity_id, new_name, sup_uploaded_photo, config.BOT_USERNAME)
                    if not success:
                        mutation_success = False
                        max_flood_time = max(max_flood_time, flood_seconds)
            else:
                logger.info(f"🦇 [ÓRFÃO] [{new_name}]. SUPORTE ASSUMIU.")
                final_entity_id, success, flood_seconds = await self._execute_mutations(self.support_client, entity_id, new_name, sup_uploaded_photo, config.BOT_USERNAME)
                if not success:
                    mutation_success = False
                    max_flood_time = max(max_flood_time, flood_seconds)

            if not mutation_success:
                logger.warning(f"↪️ Grupo {new_name} enviado para a fila de Repescagem!")
                retry_queue.append(group)
                continue

            # ETAPA PIN
            logger.info("   -> [4/4] Cravação permanente da mensagem do topo (SUPORTE)...")
            try:
                try:
                    proper_id = final_entity_id
                    if not str(final_entity_id).startswith('-100'):
                        proper_id = int(f"-100{final_entity_id}")
                    await self.support_client.get_entity(proper_id)
                except Exception:
                    await self.support_client.get_dialogs(limit=30)
                    
                with open(os.path.join(DATA_DIR, 'pinned_message.txt'), 'r', encoding='utf-8') as f:
                    pin_text = f.read()

                banner_path = os.path.join(BASE_DIR, 'banner_fixado.png')
                if os.path.exists(banner_path):
                    if len(pin_text) > 1000:
                        msg_to_pin = await self.support_client.send_file(proper_id, banner_path)
                        await self.support_client.send_message(proper_id, pin_text, parse_mode='html')
                    else:
                        msg_to_pin = await self.support_client.send_file(proper_id, banner_path, caption=pin_text, parse_mode='html')
                else:
                    msg_to_pin = await self.support_client.send_message(proper_id, pin_text, parse_mode='html')
                
                await self.support_client.pin_message(proper_id, msg_to_pin.id, notify=True)
                
                group['status'] = 'MUTADO'
                self.persistence.save_state(groups)
                self.persistence.save_production_group(proper_id, new_name, group.get("link", ""))
                logger.info(f"✅ CONCLUÍDO: [{new_name}] blindado.")
                
            except FloodWaitError as e:
                logger.warning(f"⏳ FLOODWAIT no Suporte ao Pinar! Tempo: {e.seconds}s. Grupo foi para a Repescagem.")
                retry_queue.append(group)
                max_flood_time = max(max_flood_time, e.seconds)
            except Exception as e:
                logger.warning(f"Atenção não-fatal ao fixar: {e}")
                group['status'] = 'MUTADO'
                self.persistence.save_state(groups)

            await asyncio.sleep(random.uniform(5, 10))

        if retry_queue:
            logger.warning(f"\n==========================================")
            logger.warning(f"🚦 FINAL DA LINHA ALCANÇADO. Repescagem Ativada!")
            logger.warning(f"Temos {len(retry_queue)} grupos aguardando alívio de limite do telegram.")
            logger.warning(f"😴 Entrando em sono profundo por {max_flood_time + 10} segundos.")
            logger.warning(f"==========================================\n")
            
            await asyncio.sleep(max_flood_time + 10)
            
            logger.info("🔥 Despertando e processando a repescagem...")
            return await self.run_fleet()

        logger.info("🧊 Pipeline Encerrado com 0 pendentes.")
        await self.support_client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    mutator = FleetOrchestrator()
    asyncio.run(mutator.run_fleet())
