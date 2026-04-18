import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from telethon import TelegramClient
from telethon.tl.types import Channel, InputChatUploadedPhoto
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.functions.messages import EditChatAboutRequest, EditChatTitleRequest, EditChatPhotoRequest
from telethon.tl.functions.channels import EditTitleRequest, EditPhotoRequest as ChannelEditPhotoRequest

from core.settings import config, SESSION_DIR, DATA_DIR, BASE_DIR
from data.state_manager import StateMachine

# Logger de Desempenho
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("MOTOR_CENTRAL")

class FleetRunner:
    def __init__(self):
        self.sm = StateMachine()
        # O Mestre Executivo (Suporte) roda conectado permanentemente no kernel
        master_session = os.path.join(SESSION_DIR, 'suporte_oficial.session')
        self.master = TelegramClient(master_session, config.API_ID, config.API_HASH, flood_sleep_threshold=0)
        
        self.new_about = self._read_file(os.path.join(DATA_DIR, 'group_description.txt'))
        self.pin_text = self._read_file(os.path.join(DATA_DIR, 'pinned_message.txt'))
        self.banner_path = os.path.join(BASE_DIR, config.AVATAR_PATH) # Ou outro banner se existir.

    def _read_file(self, path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return ""

    async def _safe_execute(self, client, coro):
        """Camada estrita contra falhas letais"""
        try:
            await coro
            return True, 0
        except FloodWaitError as e:
            return False, e.seconds
        except Exception as e:
            logger.debug(f"Erro em operação física: {e}")
            return True, 0 # Ignora falhas permanentes de privilégio e força o progresso O(1)

    async def perform_master_post(self, entity_id):
        """O Mestre intercede e posta a propaganda"""
        try:
            proper_id = int(f"-100{entity_id}") if not str(entity_id).startswith('-100') else int(entity_id)
            entity = await self.master.get_entity(proper_id)
            
            if os.path.exists(self.banner_path):
                await self.master.send_file(entity, self.banner_path, caption=self.pin_text, parse_mode='html')
            else:
                await self.master.send_message(entity, self.pin_text, parse_mode='html')
            return True, 0
        except FloodWaitError as e:
            return False, e.seconds
        except Exception as e:
            logger.error(f"Erro do Mestre ao Postar anúncio: {e}")
            return False, -1 # Erro fatal de permissão no mestre

    async def run(self):
        await self.master.connect()
        if not await self.master.is_user_authorized():
            logger.error("🛑 MESTRE NÃO ESTÁ AUTORIZADO. Configure a sessão do suporte primeiro.")
            return

        logger.info("🟢 Mestre Executivo Acoplado. Sistema Online.")

        while True:
            person = self.sm.get_next_person()
            if not person:
                logger.info("🧊 ZERO FILAS ALOCADAS. Todas as contas finalizaram o pipeline perfeitamente. Hibernando...")
                break

            logger.info(f"⚡ Roteando processamento atômico para a pessoa: [{person}]")
            
            # Arquitetura de Sessão por Pessoa (A sessão deve se chamar 'Nome_da_Pessoa.session')
            person_session_name = person.replace(" ", "_").lower()
            session_path = os.path.join(SESSION_DIR, f"{person_session_name}.session")
            
            if person == "SUPORTE OFICIAL":
                worker = self.master # O suporte faz o papel do próprio Worker
            else:
                worker = TelegramClient(session_path, config.API_ID, config.API_HASH, flood_sleep_threshold=0)
                await worker.connect()
                if not await worker.is_user_authorized():
                    logger.warning(f"Sessão ausente/deslogada para [{person_session_name}]. Abortando pessoa O(1).")
                    self.sm.state[person]["status"] = "ESVAZIADO" # Remove do circuito por falha estrutural
                    self.sm._commit()
                    await worker.disconnect()
                    continue

            # Extração de Foto Global
            photo_file = await worker.upload_file(self.banner_path) if os.path.exists(self.banner_path) else None

            groups_dict = self.sm.state[person]["groups"]
            person_blocked = False

            for g_id_str, g_data in groups_dict.items():
                if person_blocked: 
                    break

                entity_id = int(g_id_str)
                proper_id = int(f"-100{entity_id}") if not str(entity_id).startswith('-100') else int(entity_id)

                try:
                    entity = await worker.get_entity(proper_id)
                except Exception:
                    # Falha em pegar a entidade localmente. Droppando
                    continue

                new_name = f"🕵️‍♂️ 𝗩Λ𝗥𝗥𝗘𝗗𝗨𝗥Λ 𝗚𝗥Λ́𝗧𝗜𝗦 ［#{g_data['internal_code']}］ ⚡️ 〘 𝗜Λ 𝗗𝗘𝗧𝗘𝗧𝗜𝗩𝗘 〙" if g_data["internal_code"] != "NONE" else "🕵️‍♂️ 𝗩Λ𝗥𝗥𝗘𝗗𝗨𝗥Λ 𝗚𝗥Λ́𝗧𝗜𝗦"

                actions = g_data["actions"]

                # 1. DELETE HISTORY
                if actions["clear_history"] == "PENDENTE":
                    logger.info(f"   [{person}] -> Limpando Entropia no grupo {g_id_str}")
                    try:
                        async for msg in worker.iter_messages(entity, limit=30):
                            await msg.delete()
                        self.sm.mark_action_done(person, g_id_str, "clear_history")
                    except FloodWaitError as e:
                        self.sm.apply_thermal_block(person, e.seconds)
                        person_blocked = True; continue

                # 2. CHANGE NAME
                if actions["change_name"] == "PENDENTE":
                    logger.info(f"   [{person}] -> Trocando Titulo: {new_name}")
                    req = EditTitleRequest(channel=entity, title=new_name) if isinstance(entity, Channel) else EditChatTitleRequest(chat_id=proper_id, title=new_name)
                    success, f_sec = await self._safe_execute(worker, worker(req))
                    if success: self.sm.mark_action_done(person, g_id_str, "change_name")
                    elif f_sec > 0: self.sm.apply_thermal_block(person, f_sec); person_blocked = True; continue

                # 3. CHANGE DESC
                if actions["change_desc"] == "PENDENTE":
                    logger.info(f"   [{person}] -> Modificando Descricao")
                    req = EditChatAboutRequest(peer=entity, about=self.new_about)
                    success, f_sec = await self._safe_execute(worker, worker(req))
                    if success: self.sm.mark_action_done(person, g_id_str, "change_desc")
                    elif f_sec > 0: self.sm.apply_thermal_block(person, f_sec); person_blocked = True; continue

                # 4. CHANGE PHOTO
                if actions["change_photo"] == "PENDENTE" and photo_file:
                    logger.info(f"   [{person}] -> Alterando Visual")
                    req = ChannelEditPhotoRequest(channel=entity, photo=InputChatUploadedPhoto(file=photo_file)) if isinstance(entity, Channel) else EditChatPhotoRequest(chat_id=proper_id, photo=InputChatUploadedPhoto(file=photo_file))
                    success, f_sec = await self._safe_execute(worker, worker(req))
                    if success: self.sm.mark_action_done(person, g_id_str, "change_photo")
                    elif f_sec > 0: self.sm.apply_thermal_block(person, f_sec); person_blocked = True; continue

                # 5. MASTER POSTS AD
                if actions["support_post"] == "PENDENTE":
                    logger.info(f"   [MESTRE] -> Depositando Anuncio")
                    success, f_sec = await self.perform_master_post(proper_id)
                    if success: self.sm.mark_action_done(person, g_id_str, "support_post")
                    elif f_sec > 0: 
                        logger.warning(f"⚠️ Mestre Bloqueado Thermalmente! Aguardando {f_sec}s forçado.")
                        await asyncio.sleep(f_sec) # O Mestre tem que paralisar, ele é único.
                        continue

                # 6. OWNER PINS
                if actions["owner_pin"] == "PENDENTE":
                    logger.info(f"   [{person}] -> Fixando a Propaganda")
                    try:
                        msgs = await worker.get_messages(entity, limit=3)
                        for m in msgs:
                            if m.sender_id == self.master.session.id or m.media: # Pin na mensagem do bot recem jogada
                                await worker.pin_message(entity, m.id, notify=True)
                                break
                        self.sm.mark_action_done(person, g_id_str, "owner_pin")
                    except FloodWaitError as e:
                        self.sm.apply_thermal_block(person, e.seconds)
                        person_blocked = True; continue

                asyncio.sleep(3) # Delay entropico leve entre grupos da mesma pessoa
            
            if person != "SUPORTE OFICIAL":
                await worker.disconnect()

        await self.master.disconnect()

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    runner = FleetRunner()
    asyncio.run(runner.run())
