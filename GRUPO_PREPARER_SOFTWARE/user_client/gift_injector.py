import sys
import os
import re
import json
import asyncio
import logging

# Garante path injection para o core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from telethon import TelegramClient
from telethon.tl.types import Channel, ChatAdminRights
from telethon.tl.functions.channels import InviteToChannelRequest, EditAdminRequest
from telethon.tl.functions.messages import AddChatUserRequest
from telethon.errors.rpcerrorlist import FloodWaitError, UserPrivacyRestrictedError

from core.settings import config, SESSION_DIR, DATA_DIR, BASE_DIR

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("INJETOR_GIFTS")

class GiftInjector:
    def __init__(self):
        # Mestre executivo usa a sessão de suporte principal já aquecida na pasta sessions/
        master_session = os.path.join(SESSION_DIR, 'user_account.session')
             
        self.master = TelegramClient(master_session, config.API_ID, config.API_HASH, flood_sleep_threshold=0)
        self.bot_target = "@IADetetive_bot"
        self.accounts_map = []
        
        mapping_path = os.path.join(DATA_DIR, 'accounts_mapping.json')
        if os.path.exists(mapping_path):
            with open(mapping_path, 'r', encoding='utf-8') as f:
                self.accounts_map = json.load(f)

    async def generate_gift_code(self):
        """Mestre pede o gift ao bot e escuta a resposta restritamente (Delay de 2s)"""
        try:
            await self.master.send_message(self.bot_target, "/gift 500")
            await asyncio.sleep(2) # Delay crítico para propagação da resposta da rede
            
            async for msg in self.master.iter_messages(self.bot_target, limit=3):
                if msg.out: continue 
                
                text = msg.text or ""
                # EXTRATOR O(1): Segmentação semântica ancorada pela label "Código:"
                match = re.search(r'Código:\s*([A-Z0-9\-]+)', text, re.IGNORECASE)
                
                if match:
                    return match.group(1), 0
                    
            return "NENHUM_CODIGO_DETECTADO", 0 
        except FloodWaitError as e:
            return None, e.seconds
        except Exception as e:
            logger.error(f"Falha na geração matricial: {e}")
            return None, -1

    async def ensure_bot_in_group(self, worker, entity, bot_entity):
        """Drone tenta inserir o bot no canal e alterar seu nível de permissão"""
        try:
            if isinstance(entity, Channel):
                await worker(InviteToChannelRequest(entity, [bot_entity]))
            else:
                await worker(AddChatUserRequest(entity.id, bot_entity, fwd_limit=0))
        except Exception as e:
            if "already" not in str(e).lower() and "already a participant" not in str(e):
                logger.debug(f"Tentativa de adição marginal (Ignorada): {e}")

        try:
            rights = ChatAdminRights(
                change_info=True, post_messages=True, edit_messages=True,
                delete_messages=True, ban_users=True, invite_users=True,
                pin_messages=True, manage_call=True
            )
            if isinstance(entity, Channel):
                await worker(EditAdminRequest(channel=entity, user_id=bot_entity, admin_rights=rights, rank="Admin IA"))
        except Exception as e:
             if "ChatAdminRequiredError" not in str(e.__class__.__name__):
                logger.debug(f"Promover Admin marginal (Ignorada): {e}")

    async def run(self):
        await self.master.connect()
        if not await self.master.is_user_authorized():
            logger.error("🛑 MESTRE NÃO ESTÁ AUTORIZADO. Pipeline Invalido (Nível Root).")
            return

        logger.info("🟢 Pipeline de Injeção de Gifts Estocásticos INICIALIZADO.")
        
        try:
            await self.master.get_input_entity(self.bot_target)
        except Exception as e:
            logger.error(f"⚠️ Entidade do bot alvo não alocada pelo mestre. Abortando. {e}")
            return

        for acc in self.accounts_map:
            person = acc.get("name", "Desconhecido")
            phone = acc.get("phone")
            groups = acc.get("groups", [])
            
            if not groups: continue
            
            logger.info(f"⚡ Contexto alocado para o Owner: [{person}] ({len(groups)} grupos matriculados).")
            session_path = os.path.join(BASE_DIR, 'user_client', 'sessions', f"{phone}.session")
            
            if not os.path.exists(session_path):
                logger.warning(f"Sessão ausente para {phone}. Skip O(1).")
                continue

            worker = TelegramClient(session_path, acc.get('api_id', config.API_ID), acc.get('api_hash', config.API_HASH), flood_sleep_threshold=0)
            await worker.connect()
            
            if not await worker.is_user_authorized():
                logger.warning(f" Drone [{person}] sofreu desautenticação. Skip.")
                await worker.disconnect()
                continue
                
            try:
                worker_bot_ent = await worker.get_input_entity(self.bot_target)
            except:
                worker_bot_ent = self.bot_target

            # Processamento Sub-Matricial (Grupos)
            dialogs = await worker.get_dialogs(limit=100)
            
            for g_code in groups:
                entity = None
                for d in dialogs:
                    if g_code in d.name:
                        entity = d.entity
                        break
                
                if not entity: continue

                logger.info(f"   -> Fluxo [{person}] >> [{getattr(entity, 'title', g_code)}]")

                logger.info("      [MESTRE] Requisitando e processando Gift em PM...")
                gift_code, flood_s = await self.generate_gift_code()
                
                if flood_s > 0:
                    logger.warning(f"      [MESTRE] Teto térmico da API. Hibernando por {flood_s}s...")
                    await asyncio.sleep(flood_s + 5)
                    continue
                elif gift_code == "NENHUM_CODIGO_DETECTADO":
                    logger.error("      [MESTRE] Falha de extração do RegEx (Substitua na Linha 46). Abortando este nó e prosseguindo.")
                    continue

                logger.info(f"      [MESTRE] ✅ Hash Extraído e Pronto: {gift_code}")

                # Passo C — [DRONE] Concede privilégios Ring-0 ao Bot (ANTES do resgate)
                logger.info("      [DRONE] Concedendo privilégios Ring-0 ao Bot.")
                await self.ensure_bot_in_group(worker, entity, worker_bot_ent)

                # Passo D — [MESTRE] Resgata o gift no grupo (bot já está admin)
                logger.info(f"      [MESTRE] Injetando resgate no grupo...")
                try:
                    await self.master.send_message(entity, f"/resgatar_gift {gift_code}")
                except FloodWaitError as e:
                    logger.warning(f"      [MESTRE] Flood no resgate. Paralisando por {e.seconds}s.")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.error(f"      [MESTRE] Falha na rede ao despachar resgate: {e}")

                # Limitador entrópico - Evita o shadow ban da API de convite ao bot
                await asyncio.sleep(4) 

            await worker.disconnect()

        await self.master.disconnect()
        logger.info("🧊 Saturação de frotas completa. Encerramento Zero-Leak.")

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    inj = GiftInjector()
    asyncio.run(inj.run())
