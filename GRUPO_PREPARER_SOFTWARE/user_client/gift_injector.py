import sys
import os
import re
import json
import asyncio
import logging
from datetime import datetime, timezone

# Garante path injection para o core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from telethon import TelegramClient
from telethon.tl.types import Channel, ChatAdminRights, ChatBannedRights
from telethon.tl.functions.channels import InviteToChannelRequest, EditAdminRequest, EditBannedRequest
from telethon.tl.functions.messages import AddChatUserRequest, EditChatDefaultBannedRightsRequest
from telethon.errors.rpcerrorlist import FloodWaitError, UserPrivacyRestrictedError

from core.settings import config, SESSION_DIR, DATA_DIR, BASE_DIR

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("INJETOR_GIFTS")
GIFT_STATE_PATH = os.path.join(DATA_DIR, 'gift_injection_state.json')

class GiftInjector:
    def __init__(self):
        # Mestre executivo usa a sessão de suporte principal já aquecida na pasta sessions/
        master_session = os.path.join(SESSION_DIR, 'user_account.session')
              
        self.master = TelegramClient(master_session, config.API_ID, config.API_HASH, flood_sleep_threshold=0)
        self.bot_target = "@IADetetive_bot"
        self.accounts_map = []
        self.injection_state = self._load_state()
        
        mapping_path = os.path.join(DATA_DIR, 'accounts_mapping.json')
        if os.path.exists(mapping_path):
            with open(mapping_path, 'r', encoding='utf-8') as f:
                self.accounts_map = json.load(f)

    def _load_state(self) -> dict:
        base_state = {
            "version": 1,
            "groups": {},
            "generated_codes": {}
        }

        if not os.path.exists(GIFT_STATE_PATH):
            return base_state

        try:
            with open(GIFT_STATE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return base_state
            if "groups" not in data:
                data["groups"] = {}
            if "generated_codes" not in data:
                data["generated_codes"] = {}
            return data
        except Exception as e:
            logger.warning(f"[ESTADO] Falha ao ler cache persistente de gifts ({e}). Reiniciando estado limpo.")
            return base_state

    def _persist_state(self) -> None:
        try:
            with open(GIFT_STATE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.injection_state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[ESTADO] Falha ao salvar estado persistente de gifts: {e}")

    def _group_key(self, group_id: int) -> str:
        return str(group_id)

    def _group_record(self, group_id: int) -> dict:
        return self.injection_state["groups"].setdefault(self._group_key(group_id), {})

    def _is_group_done(self, group_id: int) -> bool:
        group = self._group_record(group_id)
        return group.get("status") == "DONE"

    def _stored_code_for_group(self, group_id: int) -> str | None:
        group = self._group_record(group_id)
        if isinstance(group.get("code"), str):
            return group["code"]
        return None

    def _store_group_code(self, group_id: int, code: str, owner: str, phone: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        gkey = self._group_key(group_id)
        group = self.injection_state["groups"].setdefault(gkey, {})
        if group.get("code") != code:
            self.injection_state["generated_codes"][code] = {
                "group_id": group_id,
                "owner": owner,
                "phone": phone,
                "generated_at": now,
                "status": "PENDENTE"
            }
        group.update({
            "owner": owner,
            "phone": phone,
            "code": code,
            "status": group.get("status", "PENDENTE"),
            "generated_at": group.get("generated_at", now)
        })
        self._persist_state()

    def _mark_group_done(self, group_id: int, code: str, owner: str, phone: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        gkey = self._group_key(group_id)
        self.injection_state["groups"][gkey] = {
            "owner": owner,
            "phone": phone,
            "code": code,
            "status": "DONE",
            "done_at": now,
            "generated_at": self.injection_state["groups"].get(gkey, {}).get("generated_at", now)
        }
        if code in self.injection_state["generated_codes"]:
            self.injection_state["generated_codes"][code]["status"] = "DONE"
            self.injection_state["generated_codes"][code]["done_at"] = now
        self._persist_state()

    def _extract_gift_code(self, text: str | None) -> str | None:
        if not text:
            return None

        # Remove formatação do Telegram que o bot injeta na mensagem.
        clean = text.replace('`', '').replace('*', '').replace('_', '')

        # Ex.: "Código: SYNTAX-88D19F1D"
        match = re.search(r'c[oó]digo:\s*([A-Z0-9][A-Z0-9-]{5,})', clean, re.IGNORECASE)
        if match:
            return match.group(1)

        # Ex.: marcação genérica em destaque: SYNTAX-88D19F1D
        match = re.search(r'\b([A-Z]{2,}-[A-Z0-9]{6,})\b', clean)
        if match:
            return match.group(1)

        # Fallback final para tokens de alta entropia usados pelo bot.
        fallback = re.findall(r'\b([A-Z0-9]{8,})\b', clean)
        return fallback[0] if fallback else None

    async def generate_gift_code(self):
        """Mestre pede o gift ao bot e escuta a resposta restritamente (Delay de 2s)"""
        try:
            await self.master.send_message(self.bot_target, "/gift 500")
            await asyncio.sleep(2) # Delay crítico para propagação da resposta da rede
            
            async for msg in self.master.iter_messages(self.bot_target, limit=3):
                if msg.out: continue 
                
                text = msg.text or ""
                # DEBUG: log do texto real para ajuste do regex
                logger.debug(f"Resposta do bot (raw): {text[:500]}")
                code = self._extract_gift_code(text)
                if code:
                    return code, 0
                     
            return "NENHUM_CODIGO_DETECTADO", 0
        except FloodWaitError as e:
            return None, e.seconds
        except Exception as e:
            logger.error(f"Falha na geração matricial: {e}")
            return None, -1

    async def unlock_group_messaging(self, worker, entity):
        """Drone libera envio de mensagens no grupo (remove slowmode/ban global)"""
        try:
            if isinstance(entity, Channel):
                # EditBannedRequest(channel, user_id, banned_rights) — positional args
                await worker(EditBannedRequest(
                    entity,
                    0,
                    ChatBannedRights(
                        until_date=None,
                        send_messages=False,
                        send_media=False,
                        send_stickers=False,
                        send_gifs=False,
                        send_games=False,
                        send_inline=False,
                        embed_links=False
                    )
                ))
            else:
                await worker(EditChatDefaultBannedRightsRequest(
                    peer=entity,
                    default_banned_rights=ChatBannedRights(
                        until_date=None,
                        send_messages=False,
                        send_media=False,
                        send_stickers=False,
                        send_gifs=False,
                        send_games=False,
                        send_inline=False,
                        embed_links=False
                    )
                ))
            logger.info("      [DRONE] ✅ Permissões de envio liberadas.")
        except Exception as e:
            logger.warning(f"      [DRONE] Falha ao liberar envio: {e}")

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
            # Index por ID para lookup O(1)
            dialog_map = {d.id: d.entity for d in dialogs}
            
            for g in groups:
                g_code = g.get("code", "")
                g_id = g.get("id")
                
                entity = dialog_map.get(g_id)
                
                if not entity:
                    logger.warning(f"      Grupo [{g_code}] (ID:{g_id}) não encontrado nos dialogs do worker [{person}]. Skip.")
                    continue

                logger.info(f"   -> Fluxo [{person}] >> [{getattr(entity, 'title', g_code)}]")

                if self._is_group_done(g_id):
                    logger.info(f"      [MESTRE] Grupo já concluído anteriormente. Pulando e retomando do estado persistente.")
                    continue

                logger.info("      [MESTRE] Requisitando e processando Gift em PM...")
                saved_code = self._stored_code_for_group(g_id)
                if saved_code:
                    gift_code = saved_code
                    flood_s = 0
                    logger.info(f"      [MESTRE] ♻️  Gift reaproveitado do histórico persistente: {gift_code}")
                else:
                    gift_code, flood_s = await self.generate_gift_code()
                    if gift_code not in (None, "NENHUM_CODIGO_DETECTADO"):
                        self._store_group_code(g_id, gift_code, person, phone)
                    elif gift_code is None:
                        logger.error("      [MESTRE] Falha operacional ao pedir gift ao bot.")
                        continue
                 
                if flood_s > 0:
                    logger.warning(f"      [MESTRE] Teto térmico da API. Hibernando por {flood_s}s...")
                    await asyncio.sleep(flood_s + 5)
                    continue
                elif gift_code in (None, "NENHUM_CODIGO_DETECTADO"):
                    logger.error("      [MESTRE] Falha de extração do RegEx (Substitua na Linha 46). Abortando este nó e prosseguindo.")
                    continue

                logger.info(f"      [MESTRE] ✅ Hash Extraído e Pronto: {gift_code}")

                # Passo B — [DRONE] Libera envio de mensagens no grupo
                logger.info("      [DRONE] Liberando envio de mensagens no grupo.")
                await self.unlock_group_messaging(worker, entity)

                # Passo C — [DRONE] Concede privilégios Ring-0 ao Bot (ANTES do resgate)
                logger.info("      [DRONE] Concedendo privilégios Ring-0 ao Bot.")
                await self.ensure_bot_in_group(worker, entity, worker_bot_ent)

                # Passo D — [MESTRE] Resgata o gift no grupo (bot já está admin)
                logger.info(f"      [MESTRE] Injetando resgate no grupo...")
                try:
                    # O alvo é o ID do grupo para evitar serialização inválida entre clientes.
                    # (entity do worker nem sempre é reusável pelo mestre na mesma sessão).
                    try:
                        await self.master.send_message(int(g_id), f"/resgatar_gift {gift_code}")
                    except FloodWaitError:
                        raise
                    except Exception:
                        await self.master.send_message(str(g_id), f"/resgatar_gift {gift_code}")

                    self._mark_group_done(g_id, gift_code, person, phone)
                    logger.info(f"      [MESTRE] ✅ Gift aplicado e marcado como concluído: {gift_code}")
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
