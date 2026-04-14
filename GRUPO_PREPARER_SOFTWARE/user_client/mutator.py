import sys
import os
import re
import json
import random
import logging
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from telethon import TelegramClient
from telethon.tl.types import Chat, Channel, InputChatUploadedPhoto, ChatAdminRights
from telethon.tl.functions.channels import EditAdminRequest, EditTitleRequest, EditPhotoRequest as ChannelEditPhotoRequest
from telethon.tl.functions.messages import EditChatAboutRequest, EditChatTitleRequest, EditChatPhotoRequest
from telethon.errors.rpcerrorlist import ChatNotModifiedError, FloodWaitError
from core.settings import config, SESSION_DIR, BASE_DIR, DATA_DIR
from data.io_manager import PersistenceManager
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import telethon.network.mtprotostate
telethon.network.mtprotostate.MSG_TOO_OLD_DELTA = 999999999
telethon.network.mtprotostate.MSG_TOO_NEW_DELTA = 999999999

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
                                             device_model="Desktop Windows", flood_sleep_threshold=0) # Must be 0 to catch and bypass
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

    async def _execute_aesthetic_mutations(self, client, entity_id, new_name, uploaded_photo, new_about):
        try:
            proper_id = entity_id
            if not str(entity_id).startswith('-100'):
                proper_id = int(f"-100{entity_id}")

            try:
                entity = await client.get_entity(proper_id)
            except Exception:
                await client.get_dialogs(limit=50) 
                try:
                    entity = await client.get_entity(proper_id)
                except Exception as e:
                    logger.error(f"Erro fatal: Conta de Mutação NÃO ESTÁ O GRUPO: {e}")
                    return entity_id, False, 0
                    
            if hasattr(entity, 'migrated_to') and entity.migrated_to is not None:
                entity = await client.get_entity(entity.migrated_to)
                
            entity_id = entity.id

            logger.info("   -> [1/4] Aniquilando resíduos anteriores...")
            async for msg in client.iter_messages(entity_id, limit=30):
                await msg.delete()

            logger.info("   -> [2/4] Sobrescrevendo Título, Descrição e Foto...")
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
            logger.warning(f"⏳ SPAM (FloodWait Estético): Tempo residual exigido é de {e.seconds}s.")
            return entity_id, False, e.seconds
        except Exception as e:
            logger.error(f"Erro na etapa de mutação estética: {e}")
            return entity_id, False, 0

    async def _promote_bot(self, client, entity_id, bot_entity_str):
        try:
            proper_id = entity_id
            if not str(entity_id).startswith('-100'):
                proper_id = int(f"-100{entity_id}")
            entity = await client.get_entity(proper_id)
            if isinstance(entity, Channel):
                rights = ChatAdminRights(change_info=True, post_messages=True, edit_messages=True, delete_messages=True, ban_users=True, invite_users=True, pin_messages=True, manage_call=True)
                try: await client(EditAdminRequest(channel=entity, user_id=bot_entity_str, admin_rights=rights, rank="Bot Oficial"))
                except FloodWaitError as e: raise e
                except Exception as e:
                    pass
            return True, 0
        except FloodWaitError as e:
            logger.warning(f"⏳ SPAM (FloodWait BOT Promoção): {e.seconds}s.")
            return False, e.seconds
        except Exception as e:
            return True, 0

    async def _execute_pin(self, entity_id, pin_text, banner_path):
        try:
            proper_id = entity_id
            if not str(entity_id).startswith('-100'):
                proper_id = int(f"-100{entity_id}")

            try:
                await self.support_client.get_entity(proper_id)
            except Exception:
                await self.support_client.get_dialogs(limit=30)
                
            msg_to_pin = None
            if os.path.exists(banner_path):
                if len(pin_text) > 1000:
                    msg_to_pin = await self.support_client.send_file(proper_id, banner_path)
                    await self.support_client.send_message(proper_id, pin_text, parse_mode='html')
                else:
                    msg_to_pin = await self.support_client.send_file(proper_id, banner_path, caption=pin_text, parse_mode='html')
            else:
                msg_to_pin = await self.support_client.send_message(proper_id, pin_text, parse_mode='html')
            
            try:
                await self.support_client.pin_message(proper_id, msg_to_pin.id, notify=True)
            except FloodWaitError as e: raise e
            except Exception as e:
                pass
                
            return True, 0
        except FloodWaitError as e:
            logger.warning(f"⏳ SPAM no fixamento do PIN O(1): Aguardo {e.seconds}s.")
            return False, e.seconds
        except Exception as e:
            logger.error(f"⚠️ Erro inalienável ao fixar: {e}")
            return False, 0

    async def run_fleet(self, test_mode=False, iteration_groups=None):
        if not self.support_client.is_connected():
            await self.support_client.start(phone=config.PHONE)
            logger.info("👑 CÉREBRO: Conexão MAESTRO estabelecida em nível Root.")

        groups_to_process = iteration_groups
        groups_db = self.persistence.load_state()

        if groups_to_process is None:
            groups_to_process = groups_db
            if not groups_to_process:
                return

        sup_uploaded_photo = None
        if os.path.exists(config.AVATAR_PATH):
            sup_uploaded_photo = await self.support_client.upload_file(config.AVATAR_PATH)

        with open(os.path.join(DATA_DIR, 'group_description.txt'), 'r', encoding='utf-8') as f:
            new_about = f.read()
        
        with open(os.path.join(DATA_DIR, 'pinned_message.txt'), 'r', encoding='utf-8') as f:
            pin_text = f.read()

        banner_path = os.path.join(BASE_DIR, 'banner_fixado.png')
        bot_entity_str = config.BOT_USERNAME

        retry_queue = []
        max_flood_time = 0

        for group in groups_to_process:
            entity_id = group["id"]
            new_name = group.get("new_name", "").strip()
            
            db_group_ref = next((g for g in groups_db if g["id"] == entity_id), group)
            
            if db_group_ref.get("status") == "MUTADO":
                continue
            if not new_name:
                continue

            logger.info(f"⚡ Disparando rotina O(1) de Controle em: [{new_name}]")
            owner = self.get_owner_for_group(new_name)
            final_entity_id = entity_id
            aesthetic_success = True

            if owner:
                logger.info(f"👥 [DELEGAÇÃO SATÉLITE] Encarregado: {owner['name']}.")
                session_path = os.path.join(BASE_DIR, 'user_client', 'sessions', f"{owner['phone']}.session")
                
                if os.path.exists(session_path):
                    worker = TelegramClient(session_path, owner['api_id'], owner['api_hash'], flood_sleep_threshold=0)
                    await worker.connect()
                    if await worker.is_user_authorized():
                        worker_photo = await worker.upload_file(config.AVATAR_PATH) if os.path.exists(config.AVATAR_PATH) else None
                        
                        final_entity_id, success, flood_seconds = await self._execute_aesthetic_mutations(worker, entity_id, new_name, worker_photo, new_about)
                        if not success:
                            aesthetic_success = False
                            max_flood_time = max(max_flood_time, flood_seconds)
                    else:
                        logger.warning(f"⚠️ Worker falhou a conexão. Mestre Executivo cobrindo...")
                        final_entity_id, success, flood_seconds = await self._execute_aesthetic_mutations(self.support_client, entity_id, new_name, sup_uploaded_photo, new_about)
                        if not success:
                            aesthetic_success = False
                            max_flood_time = max(max_flood_time, flood_seconds)
                    await worker.disconnect()
                else:
                    final_entity_id, success, flood_seconds = await self._execute_aesthetic_mutations(self.support_client, entity_id, new_name, sup_uploaded_photo, new_about)
                    if not success:
                        aesthetic_success = False
                        max_flood_time = max(max_flood_time, flood_seconds)
            else:
                final_entity_id, success, flood_seconds = await self._execute_aesthetic_mutations(self.support_client, entity_id, new_name, sup_uploaded_photo, new_about)
                if not success:
                    aesthetic_success = False
                    max_flood_time = max(max_flood_time, flood_seconds)

            if not aesthetic_success:
                logger.warning(f"↪️ Interrupção Termal via Drone na etapa de Mutação. Transferido O(n) para Repescagem.")
                retry_queue.append(db_group_ref)
                continue

            logger.info("   -> [3/4] Promovendo Microsserviço BOT à Orquestrador...")
            promo_ok, flood_s = await self._promote_bot(self.support_client, final_entity_id, bot_entity_str)
            if not promo_ok:
                logger.warning(f"↪️ Interrupção Termal na delegação pro BOT. Transferido O(n) para Repescagem.")
                retry_queue.append(db_group_ref)
                max_flood_time = max(max_flood_time, flood_s)
                continue

            logger.info("   -> [4/4] FIXAÇÃO ABSOLUTA DA CHAVE (VIA CONTA SUPORTE)...")
            pin_success, flood_seconds = await self._execute_pin(final_entity_id, pin_text, banner_path)
            
            if not pin_success:
                logger.warning(f"↪️ INTERRUPÇÃO DE SPAM DURANTE O PIN! Grupo preservado e despachado para a Fila Póstuma.")
                retry_queue.append(db_group_ref)
                max_flood_time = max(max_flood_time, flood_seconds)
                continue
                
            db_group_ref['status'] = 'MUTADO'
            self.persistence.save_state(groups_db)
            self.persistence.save_production_group(final_entity_id, new_name, db_group_ref.get("link", ""))
            logger.info(f"✅ CICLO COMPLETO: [{new_name}] blindado, otimizado e gravado na base de dados.")
            
            await asyncio.sleep(random.uniform(18, 32))

            if test_mode:
                logger.warning("🧪 TESTE ISOLADO TERMINAL: Encerrando execução apressada.")
                break

        if retry_queue and not test_mode:
            logger.warning(f"\n======== [ PROTEÇÃO COGNITIVA ANTI-SPAM ATIVADA ] ========")
            logger.warning(f"A Fila secundária possui {len(retry_queue)} nós bloqueados.")
            logger.warning(f"Hibernação obrigatória para esfriamento de IP: {max_flood_time + 10} segundos.")
            logger.warning(f"===========================================================\n")
            
            await asyncio.sleep(max_flood_time + 10)
            
            logger.info("🔥 Fim da hibernação. Despejando buffer e varrendo repescagem...")
            return await self.run_fleet(test_mode=False, iteration_groups=retry_queue)

        if not test_mode or not retry_queue:
            logger.info("🧊 Pipeline Principal Executado. Zero pendências de Rate-Limit.")
            await self.support_client.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    mutator = FleetOrchestrator()
    asyncio.run(mutator.run_fleet(test_mode=args.test))
