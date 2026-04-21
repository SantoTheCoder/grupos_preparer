import argparse
import asyncio
import logging
import os
import random
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import telethon.network.mtprotostate
from telethon import TelegramClient
from telethon import utils
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    EditPhotoRequest as ChannelEditPhotoRequest,
    EditTitleRequest,
    InviteToChannelRequest,
    ToggleSlowModeRequest,
)
from telethon.tl.functions.contacts import GetContactsRequest, ImportContactsRequest
from telethon.tl.functions.messages import EditChatAboutRequest, EditChatDefaultBannedRightsRequest, ExportChatInviteRequest
from telethon.tl.functions.messages import ReorderPinnedDialogsRequest, ToggleDialogPinRequest
from telethon.tl.types import ChatAdminRights, ChatBannedRights, InputChatUploadedPhoto, InputPhoneContact
from telethon.tl.types import InputDialogPeer

from core.settings import BASE_DIR, DATA_DIR, SESSION_DIR, config
from data.io_manager import PersistenceManager


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

telethon.network.mtprotostate.MSG_TOO_OLD_DELTA = 999999999
telethon.network.mtprotostate.MSG_TOO_NEW_DELTA = 999999999


log_file = os.path.join(BASE_DIR, "debug_mutator.log")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
logging.getLogger("telethon").setLevel(logging.INFO)
logger = logging.getLogger("NOVO_PIPELINE")

DRONE_SESSION_DIR = os.path.join(BASE_DIR, "user_client", "sessions")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_account_id(name: str, phone: str) -> str:
    base_name = re.sub(r"[^a-z0-9]+", "-", (name or "drone").strip().lower()).strip("-")
    digits = re.sub(r"\D", "", phone or "")
    suffix = digits[-4:] if digits else "0000"
    return f"{base_name}-{suffix}"


class GroupPipeline:
    def __init__(self):
        self.master = TelegramClient(
            config.master_session_file,
            config.API_ID,
            config.API_HASH,
            device_model="Desktop Windows",
            flood_sleep_threshold=0,
        )
        self.sub_master = TelegramClient(
            config.sub_master_session_file,
            config.SUB_MASTER_API_ID,
            config.SUB_MASTER_API_HASH,
            device_model="Desktop Windows",
            flood_sleep_threshold=0,
        )
        self.persistence = PersistenceManager()
        self.master_user = None
        self.sub_master_user = None
        self.execution_mode = None
        self.accounts = self.persistence.load_accounts()
        accounts_changed = False
        for account in self.accounts:
            if not account.get("account_id"):
                account["account_id"] = build_account_id(account.get("name", "Drone"), account.get("phone", ""))
                accounts_changed = True
        if accounts_changed:
            self.persistence.save_accounts(self.accounts)
        self.groups = self.persistence.load_groups()
        self.admin_rights = ChatAdminRights(
            change_info=True,
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=True,
            manage_call=True,
            manage_topics=True,
        )

    async def _connect_master(self):
        logger.info("[BOOT] Conectando master em %s.", config.master_session_file)
        await self.master.connect()
        logger.info("[BOOT] Master conectado. Verificando autorizacao.")
        if not await self.master.is_user_authorized():
            logger.info("[BOOT] Master sem autorizacao. Iniciando login por telefone.")
            await self.master.start(phone=config.PHONE)
        logger.info("[BOOT] Carregando identidade do master.")
        self.master_user = await self.master.get_me()
        logger.info("Master conectado com sucesso. user_id=%s", self.master_user.id)

    async def _connect_sub_master(self):
        if not config.SUB_MASTER_PHONE:
            raise RuntimeError("SUB_MASTER_PHONE nao configurado no .env.")
        if not config.SUB_MASTER_API_ID or not config.SUB_MASTER_API_HASH:
            raise RuntimeError("SUB_MASTER_API_ID/SUB_MASTER_API_HASH nao configurados no .env.")

        if not os.path.exists(config.sub_master_session_file):
            raise RuntimeError(f"Sessao do sub master nao encontrada: {config.sub_master_session_file}")

        logger.info("[BOOT] Conectando sub master em %s.", config.sub_master_session_file)
        await self.sub_master.connect()
        logger.info("[BOOT] Sub master conectado. Verificando autorizacao.")
        if not await self.sub_master.is_user_authorized():
            await self.sub_master.disconnect()
            raise RuntimeError("Sessao do sub master nao esta autorizada.")
        logger.info("[BOOT] Carregando identidade do sub master.")
        self.sub_master_user = await self.sub_master.get_me()
        logger.info("Sub master conectado com sucesso. user_id=%s", self.sub_master_user.id)

    async def _connect_drone(self, account: dict) -> TelegramClient | None:
        phone = account.get("phone")
        api_id = account.get("api_id")
        api_hash = account.get("api_hash")
        session_path = os.path.join(DRONE_SESSION_DIR, f"{phone}.session")

        if not os.path.exists(session_path):
            logger.error("Sessao do drone nao encontrada: %s", phone)
            return None

        client = TelegramClient(session_path, api_id, api_hash, flood_sleep_threshold=0)
        logger.info("[BOOT] Conectando drone [%s] em %s.", account.get("name", phone), session_path)
        await client.connect()
        logger.info("[BOOT] Drone [%s] conectado. Verificando autorizacao.", account.get("name", phone))
        if not await client.is_user_authorized():
            logger.error("Sessao do drone nao esta autorizada: %s", phone)
            await client.disconnect()
            return None

        logger.info("[BOOT] Drone [%s] pronto para operacao.", account.get("name", phone))
        return client

    def _resolve_drone_account(self, task: dict) -> dict | None:
        account_id = task.get("account_id")
        owner = task.get("owner")
        phone = task.get("phone")

        if phone and task.get("api_id") and task.get("api_hash"):
            return {
                "account_id": account_id or build_account_id(owner or "Drone", phone),
                "name": owner or "Drone",
                "phone": phone,
                "api_id": task.get("api_id"),
                "api_hash": task.get("api_hash"),
            }

        for account in self.accounts:
            if account_id and account.get("account_id") == account_id:
                return account
            if phone and account.get("phone") == phone:
                return account
            if owner and account.get("name") == owner:
                return account

        return None

    def _find_existing_record(self, task: dict) -> dict | None:
        group_id = task.get("id") or task.get("group_id")
        account_id = task.get("account_id")
        owner = task.get("owner")
        phone = task.get("phone")
        internal_code = task.get("internal_code")

        for record in self.persistence.load_groups():
            if group_id and (record.get("id") == group_id or record.get("group_id") == group_id):
                return record
            if phone and record.get("phone") == phone:
                return record
            if account_id and internal_code:
                if record.get("account_id") == account_id and record.get("internal_code") == internal_code:
                    return record
            if owner and internal_code:
                if record.get("owner") == owner and record.get("internal_code") == internal_code:
                    return record

        return None

    def _read_text_file(self, path: str) -> str:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as file_obj:
            return file_obj.read().strip()

    def _prompt_execution_mode(self) -> str:
        print("\nMODO DE EXECUCAO")
        print("1) Existe grupo")
        print("2) Do zero")

        while True:
            choice = input("Selecione o modo [1/2]: ").strip().lower()
            if choice in {"1", "existe", "existe grupo", "grupo", "existente"}:
                return "EXISTING_GROUP"
            if choice in {"2", "zero", "do zero", "novo", "criar"}:
                return "FROM_SCRATCH"
            print("Opcao invalida. Digite 1 para 'Existe grupo' ou 2 para 'Do zero'.", flush=True)

    async def _wait_flood(self, error: FloodWaitError, context: str):
        logger.warning("FloodWait em %s. Aguardando %ss.", context, error.seconds)
        await asyncio.sleep(error.seconds + 2)

    async def _safe_delay(self, reason: str, base: float | None = None, jitter: float | None = None):
        delay_base = config.ACTION_DELAY_SECONDS if base is None else base
        delay_jitter = config.ACTION_DELAY_JITTER_SECONDS if jitter is None else jitter
        total_delay = max(0.0, delay_base + random.uniform(0.0, max(0.0, delay_jitter)))
        logger.info("[DELAY] %s -> %.2fs", reason, total_delay)
        await asyncio.sleep(total_delay)

    async def _ensure_contact(self, client: TelegramClient, phone: str, first_name: str):
        try:
            logger.info("[ETAPA] Importando contato %s (%s).", first_name, phone)
            result = await client(
                ImportContactsRequest(
                    [
                        InputPhoneContact(
                            client_id=random.randint(1, 2**31 - 1),
                            phone=phone,
                            first_name=first_name or "Contato",
                            last_name="",
                        )
                    ]
                )
            )
            await self._safe_delay(f"importar contato {phone}")
            if getattr(result, "users", None):
                logger.info("[ETAPA] Contato %s resolvido com sucesso.", phone)
                return result.users[0]
            contact_user = await self._resolve_contact_from_contacts(client, phone)
            if contact_user is not None:
                logger.info("[ETAPA] Contato %s resolvido pela agenda local.", phone)
                return contact_user
            logger.info("[ETAPA] Contato %s importado sem entidade retornada.", phone)
            return None
        except FloodWaitError as error:
            await self._wait_flood(error, f"importar contato {phone}")
            return None
        except Exception as error:
            logger.warning("Falha ao importar contato %s: %s", phone, error)
            return None

    async def _resolve_contact_from_contacts(self, client: TelegramClient, phone: str):
        normalized_phone = re.sub(r"\D", "", phone or "")
        try:
            contacts = await client(GetContactsRequest(0))
        except Exception as error:
            logger.warning("Falha ao consultar agenda para %s: %s", phone, error)
            return None

        for user in getattr(contacts, "users", []):
            candidate_phone = re.sub(r"\D", "", getattr(user, "phone", "") or "")
            if candidate_phone == normalized_phone:
                return user
        return None

    async def _resolve_admin_ref_in_drone_context(self, drone: TelegramClient, label: str, phone: str, global_user):
        ref = await self._ensure_contact(drone, phone, label)
        if ref is not None:
            return ref

        username = getattr(global_user, "username", None)
        if username:
            try:
                logger.info("[ETAPA] Fallback: resolvendo %s por username @%s no contexto do drone.", label, username)
                return await drone.get_input_entity(username)
            except Exception as error:
                logger.warning("[ETAPA] Falha ao resolver %s por username: %s", label, error)

        ref = await self._resolve_contact_from_contacts(drone, phone)
        if ref is not None:
            return ref

        logger.info("[ETAPA] Fallback final: usando identidade global de %s para adicao direta.", label)
        return global_user

    async def _create_group(self, drone: TelegramClient, task: dict):
        description = self._read_text_file(config.group_description_file)
        logger.info("[ETAPA] Disparando criacao do grupo [%s].", task["name"])
        response = await drone(
            CreateChannelRequest(
                title=task["name"],
                about=description,
                megagroup=True,
            )
        )
        await self._safe_delay(f"criar grupo {task['name']}")
        created_chat = response.chats[0]
        entity = await drone.get_entity(created_chat)
        logger.info("[ETAPA] Grupo criado com id bruto %s.", getattr(entity, "id", None))

        await self._update_group_photo(drone, entity, task["name"])

        return entity

    async def _resolve_existing_group(self, drone: TelegramClient, task: dict):
        group_id = task.get("id") or task.get("group_id")
        invite_link = task.get("link") or task.get("invite_link")

        if group_id is not None:
            try:
                return await drone.get_entity(group_id)
            except Exception as error:
                logger.warning("[ETAPA] Falha ao resolver grupo por id %s: %s", group_id, error)

        if invite_link:
            try:
                return await drone.get_entity(invite_link)
            except Exception as error:
                logger.warning("[ETAPA] Falha ao resolver grupo por link %s: %s", invite_link, error)

        raise RuntimeError("Grupo existente sem id/link valido para resolucao.")

    async def _update_group_title(self, drone: TelegramClient, entity, title: str):
        try:
            logger.info("[ETAPA] Aplicando titulo normalizado do grupo.")
            await drone(EditTitleRequest(channel=entity, title=title))
            await self._safe_delay("atualizar titulo do grupo")
        except Exception as error:
            if "wasn't modified" in str(error).lower() or "not modified" in str(error).lower():
                logger.info("[ETAPA] Titulo do grupo ja estava correto.")
            else:
                raise

    async def _update_group_description(self, drone: TelegramClient, entity):
        description = self._read_text_file(config.group_description_file)
        try:
            logger.info("[ETAPA] Aplicando descricao do grupo.")
            await drone(EditChatAboutRequest(peer=entity, about=description))
            await self._safe_delay("atualizar descricao do grupo")
        except Exception as error:
            if "wasn't modified" in str(error).lower() or "not modified" in str(error).lower():
                logger.info("[ETAPA] Descricao do grupo ja estava correta.")
            else:
                raise

    async def _update_group_photo(self, drone: TelegramClient, entity, group_name: str):
        if not os.path.exists(config.avatar_file):
            logger.info("[ETAPA] Foto principal ausente. Etapa ignorada.")
            return

        uploaded = await drone.upload_file(config.avatar_file)
        await drone(
            ChannelEditPhotoRequest(
                channel=entity,
                photo=InputChatUploadedPhoto(file=uploaded),
            )
        )
        await self._safe_delay(f"aplicar foto do grupo {group_name}")

    async def _clear_group_history(self, drone: TelegramClient, entity):
        logger.info("[ETAPA] Limpando 100%% do historico visivel do grupo.")
        batch: list[int] = []

        async for message in drone.iter_messages(entity, reverse=False):
            if getattr(message, "id", None) is None:
                continue

            batch.append(message.id)
            if len(batch) >= 100:
                await drone.delete_messages(entity, batch)
                batch.clear()
                await self._safe_delay("limpar lote de mensagens", base=0.8, jitter=0.4)

        if batch:
            await drone.delete_messages(entity, batch)
            await self._safe_delay("limpar lote final de mensagens", base=0.8, jitter=0.4)

    async def _pin_group_dialog(self, drone: TelegramClient, entity):
        logger.info("[ETAPA] Fixando dialogo do grupo no topo do drone.")
        input_peer = await drone.get_input_entity(entity)
        dialog_peer = InputDialogPeer(input_peer)

        await drone(ToggleDialogPinRequest(peer=dialog_peer, pinned=True))

        dialogs = await drone.get_dialogs(limit=100)
        pinned_order = [dialog_peer]
        for dialog in dialogs:
            if not getattr(dialog, "pinned", False):
                continue

            existing_peer = InputDialogPeer(await drone.get_input_entity(dialog.entity))
            if existing_peer.peer == dialog_peer.peer:
                continue
            pinned_order.append(existing_peer)

        await drone(
            ReorderPinnedDialogsRequest(
                folder_id=0,
                order=pinned_order,
                force=True,
            )
        )
        await self._safe_delay("fixar dialogo do drone")

    async def _invite_and_promote_user(self, drone: TelegramClient, entity, user_ref, rank: str, admin_rights=None):
        try:
            logger.info("[ETAPA] Adicionando participante %s ao grupo.", rank)
            await drone(InviteToChannelRequest(entity, [user_ref]))
            await self._safe_delay(f"adicionar participante {rank}")
        except Exception as error:
            if "already" not in str(error).lower():
                raise
            logger.info("[ETAPA] Participante %s ja estava no grupo.", rank)

        logger.info("[ETAPA] Promovendo %s para admin.", rank)
        await drone(
            EditAdminRequest(
                channel=entity,
                user_id=user_ref,
                admin_rights=admin_rights or self.admin_rights,
                rank=rank,
            )
        )
        await self._safe_delay(f"promover admin {rank}")

    async def _promote_existing_user(self, drone: TelegramClient, entity, user_ref, rank: str, admin_rights=None):
        logger.info("[ETAPA] Promovendo participante existente %s para admin.", rank)
        await drone(
            EditAdminRequest(
                channel=entity,
                user_id=user_ref,
                admin_rights=admin_rights or self.admin_rights,
                rank=rank,
            )
        )
        await self._safe_delay(f"promover admin existente {rank}")

    async def _invite_bot(self, drone: TelegramClient, entity, bot_username: str, rank: str):
        logger.info("[ETAPA] Resolvendo bot %s para cargo %s.", bot_username, rank)
        bot_entity = await drone.get_input_entity(bot_username)
        await self._invite_and_promote_user(drone, entity, bot_entity, rank)
        return bot_entity

    async def _ensure_fiscal_absent_for_master_phase(self, drone: TelegramClient, entity):
        try:
            logger.info("[ETAPA] Removendo temporariamente FiscalDoGrupoBot antes da fase final do master.")
            await drone.kick_participant(entity, config.FISCAL_BOT_USERNAME)
            await self._safe_delay("remover fiscal temporariamente")
        except Exception as error:
            if "not a participant" in str(error).lower() or "could not find the input entity" in str(error).lower():
                logger.info("[ETAPA] FiscalDoGrupoBot ja nao estava presente antes da fase final.")
            else:
                raise

    async def _set_slow_mode(self, drone: TelegramClient, entity, seconds: int):
        try:
            await drone(ToggleSlowModeRequest(channel=entity, seconds=seconds))
            await self._safe_delay(f"configurar slow mode do grupo para {seconds}s")
        except Exception as error:
            if "wasn't modified" in str(error).lower() or "not modified" in str(error).lower():
                logger.info("[ETAPA] Slow mode ja estava configurado em %ss.", seconds)
            else:
                raise

    async def _configure_group_permissions(self, drone: TelegramClient, entity):
        logger.info("[ETAPA] Fechando o chat para escrita e liberando apenas add pessoas.")
        allowed_members_rights = ChatBannedRights(
            until_date=None,
            send_messages=True,
            send_media=True,
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
            send_plain=True,
        )
        try:
            await drone(EditChatDefaultBannedRightsRequest(entity, allowed_members_rights))
            await self._safe_delay("fechar chat para escrita")
        except Exception as error:
            if "wasn't modified" in str(error).lower() or "not modified" in str(error).lower():
                logger.info("[ETAPA] Permissoes padrao ja estavam aplicadas.")
            else:
                raise

    async def _extract_group_link(self, client: TelegramClient, entity) -> str:
        try:
            logger.info("[ETAPA] Exportando link de convite do grupo.")
            invite = await client(ExportChatInviteRequest(peer=entity))
            return invite.link
        except Exception:
            return ""

    async def _build_master_target(self, record: dict, entity):
        invite_link = record.get("invite_link", "")
        group_id = record.get("group_id") or utils.get_peer_id(entity)

        if invite_link:
            logger.info("[ETAPA] Resolvendo grupo do master pelo invite_link: %s.", invite_link)
            try:
                return await self.master.get_input_entity(invite_link)
            except Exception as error:
                logger.warning("[ETAPA] Falha ao resolver pelo invite_link: %s", error)

        logger.info("[ETAPA] Fallback: resolvendo grupo do master por group_id: %s.", group_id)
        return await self.master.get_input_entity(group_id)

    async def _find_group_participant(self, drone: TelegramClient, entity, user_id: int, label: str, attempts: int = 3):
        logger.info("[ETAPA] Procurando participante %s dentro do grupo.", label)
        for attempt in range(1, attempts + 1):
            participants = await drone.get_participants(entity, limit=100)
            for participant in participants:
                if participant.id == user_id:
                    logger.info("[ETAPA] Participante %s encontrado no grupo.", label)
                    return participant
            if attempt < attempts:
                logger.info("[ETAPA] Participante %s ainda nao apareceu. Nova checagem %s/%s.", label, attempt + 1, attempts)
                await asyncio.sleep(1.5)
        return None

    async def _ensure_direct_membership(self, drone: TelegramClient, entity, user_ref, user_id: int, label: str):
        participant = await self._find_group_participant(drone, entity, user_id, label, attempts=1)
        if participant is not None:
            return participant

        logger.info("[ETAPA] Adicionando %s diretamente pelo drone.", label)
        try:
            await drone(InviteToChannelRequest(entity, [user_ref]))
            await self._safe_delay(f"adicionar participante direto {label}")
        except Exception as error:
            if "already" not in str(error).lower():
                raise
            logger.info("[ETAPA] %s ja constava no grupo durante a adicao direta.", label)

        participant = await self._find_group_participant(drone, entity, user_id, label)
        if participant is None:
            raise RuntimeError(f"Participante {label} nao entrou no grupo apos adicao direta.")
        return participant

    async def _send_master_photo(self, target):
        if not os.path.exists(config.banner_file):
            return None
        logger.info("[ETAPA] Master enviando foto para o grupo.")
        message = await self.master.send_file(target, config.banner_file)
        await self._safe_delay("enviar foto do master")
        return message.id

    async def _send_master_text(self, target, text: str):
        logger.info("[ETAPA] Master enviando texto para o grupo.")
        message = await self.master.send_message(target, text, parse_mode="html", link_preview=False)
        await self._safe_delay("enviar texto do master")
        return message.id

    async def _pin_master_text(self, target, message_id: int):
        logger.info("[ETAPA] Master fixando mensagem %s.", message_id)
        await self.master.pin_message(target, message_id, notify=True)
        await self._safe_delay("fixar texto do master")

    async def _message_exists(self, target, message_id: int) -> bool:
        message = await self.master.get_messages(target, ids=message_id)
        return bool(message and getattr(message, "id", None))

    async def _redeem_gift(self, target, gift_code: str):
        logger.info("[ETAPA] Master enviando comando de resgate para o gift %s.", gift_code)
        message = await self.master.send_message(target, f"/resgatar_gift {gift_code}")
        await self._safe_delay("enviar resgate do gift")
        return message.id

    async def _generate_gift_code(self) -> str:
        logger.info("[ETAPA] Master solicitando geracao de gift ao bot %s.", config.GIFT_BOT_USERNAME)
        await self.master.send_message(config.GIFT_BOT_USERNAME, f"/gift {config.GIFT_VALUE}")
        await self._safe_delay(
            "aguardar resposta do gift bot",
            base=config.GIFT_RESPONSE_WAIT_SECONDS,
            jitter=1.0,
        )

        async for message in self.master.iter_messages(config.GIFT_BOT_USERNAME, limit=5):
            if message.out:
                continue

            text = message.text or ""
            match = re.search(r"SYNTAX-[A-Z0-9]+", text, re.IGNORECASE)
            if match:
                logger.info("[ETAPA] Gift gerado com codigo %s.", match.group(0))
                return match.group(0)

        raise RuntimeError("Nao foi possivel extrair o codigo do gift.")

    def _save_task_status(self, index: int, updates: dict):
        next_task = {**self.groups[index], **updates}
        if next_task.get("status") == "READY":
            next_task.pop("error", None)
        self.groups[index] = next_task
        self.persistence.save_groups(self.groups)
        logger.info("[STATE] runtime operacional atualizado: status=%s, group_id=%s", next_task.get("status"), next_task.get("group_id"))

    def _persist_record(self, index: int, record: dict, task_status: str):
        record["status"] = task_status
        record["updated_at"] = utc_now()
        self.persistence.upsert_group_record(record)
        logger.info("[STATE] Registro persistido em inventario/runtime com status=%s.", task_status)
        next_task = {**self.groups[index], **record}
        if next_task.get("status") == "READY":
            next_task.pop("error", None)
        self.groups[index] = next_task
        self.persistence.save_groups(self.groups)
        logger.info("[STATE] runtime operacional atualizado: status=%s, group_id=%s", next_task.get("status"), next_task.get("group_id"))

    async def _process_task(self, index: int, task: dict):
        account = self._resolve_drone_account(task)
        if not account:
            raise RuntimeError(f"Drone nao encontrado para tarefa: {task}")
        account_id = account.get("account_id") or build_account_id(account.get("name", "Drone"), account.get("phone", ""))
        account["account_id"] = account_id

        drone = await self._connect_drone(account)
        if drone is None:
            raise RuntimeError(f"Sessao do drone indisponivel: {account.get('phone')}")

        try:
            existing_record = self._find_existing_record(task) or {}
            logger.info("[ETAPA] Preparando contatos base para [%s].", task["name"])

            if self.master_user is None:
                raise RuntimeError("Master nao conectado para promocao.")
            master_ref = await self._resolve_admin_ref_in_drone_context(drone, "Master", config.PHONE, self.master_user)
            await self._ensure_contact(self.master, account["phone"], account.get("name", "Drone"))

            if self.sub_master_user is None:
                raise RuntimeError("Sub master nao conectado para promocao.")
            sub_master_ref = await self._resolve_admin_ref_in_drone_context(
                drone,
                config.SUB_MASTER_NAME,
                config.SUB_MASTER_PHONE,
                self.sub_master_user,
            )
            await self._ensure_contact(self.sub_master, account["phone"], account.get("name", "Drone"))

            if self.execution_mode == "EXISTING_GROUP":
                logger.info("[ETAPA] Reaplicando configuracao em grupo ja existente.")
                entity = await self._resolve_existing_group(drone, task)
                await self._clear_group_history(drone, entity)
                await self._update_group_photo(drone, entity, task["name"])
            else:
                logger.info("[ETAPA] Criando grupo do zero pelo drone [%s].", account.get("name"))
                entity = await self._create_group(drone, task)

            await self._update_group_title(drone, entity, task["name"])
            await self._update_group_description(drone, entity)
            await self._configure_group_permissions(drone, entity)

            logger.info("[ETAPA] Garantindo entrada direta do master pelo drone.")
            master_participant = await self._ensure_direct_membership(drone, entity, master_ref, self.master_user.id, "Master")
            await self._promote_existing_user(drone, entity, master_participant, "Master")

            logger.info("[ETAPA] Garantindo entrada direta do sub master pelo drone.")
            sub_master_participant = await self._ensure_direct_membership(
                drone,
                entity,
                sub_master_ref,
                self.sub_master_user.id,
                "Sub Master",
            )
            await self._promote_existing_user(drone, entity, sub_master_participant, "Sub Master")

            logger.info("[ETAPA] Adicionando FiscalDoGrupoBot ao grupo.")
            await self._invite_bot(drone, entity, config.FISCAL_BOT_USERNAME, "Fiscal")
            logger.info("[ETAPA] Adicionando IaDetetive_Bot ao grupo.")
            await self._invite_bot(drone, entity, config.GIFT_BOT_USERNAME, "Ia Detetive")

            invite_link = await self._extract_group_link(drone, entity)
            if not invite_link:
                raise RuntimeError("Nao foi possivel obter o link final do grupo.")

            group_id = utils.get_peer_id(entity)
            record = {
                **existing_record,
                "id": group_id,
                "group_id": group_id,
                "link": invite_link,
                "invite_link": invite_link,
                "name": task["name"],
                "group_name": task["name"],
                "owner": task.get("owner", account.get("name", "")),
                "phone": task.get("phone", account.get("phone", "")),
                "api_id": task.get("api_id", account.get("api_id")),
                "api_hash": task.get("api_hash", account.get("api_hash")),
                "account_id": account_id,
                "mode": self.execution_mode,
                "master_added": True,
                "sub_master_added": True,
                "sub_master_admin": True,
                "sub_master_name": config.SUB_MASTER_NAME,
                "sub_master_phone": config.SUB_MASTER_PHONE,
                "fiscal_bot_added": True,
                "gift_bot_added": True,
                "member_permissions_configured": True,
                "history_cleared": self.execution_mode == "EXISTING_GROUP",
                "photo_updated": True,
                "description_updated": True,
                "title_updated": True,
                "chat_locked": True,
                "created_at": existing_record.get("created_at", utc_now()),
            }
            if self.execution_mode == "FROM_SCRATCH":
                record["group_created"] = True
            else:
                record["group_reused"] = True

            self._persist_record(index, record, "READY")
            logger.info("Grupo [%s] concluido no modo [%s].", task["name"], self.execution_mode)
        finally:
            await drone.disconnect()

    async def run(self, test_mode: bool = False):
        self.groups = self.persistence.load_groups()
        if not self.groups:
            logger.warning("Base de grupos vazia. Preencha data/group_inventory.json.")
            return

        self.execution_mode = self._prompt_execution_mode()
        logger.info("Modo selecionado: %s", self.execution_mode)

        await self._connect_master()
        await self._connect_sub_master()
        processed_in_test = False

        try:
            for index, task in enumerate(self.groups):
                try:
                    await self._process_task(index, task)
                    if test_mode:
                        processed_in_test = True
                except FloodWaitError as error:
                    await self._wait_flood(error, task.get("name", "tarefa"))
                    if test_mode:
                        processed_in_test = True
                except Exception as error:
                    logger.error("Falha no grupo [%s]: %s", task.get("name", "SEM_NOME"), error)
                    self._save_task_status(
                        index,
                        {
                            "mode": self.execution_mode,
                            "status": "ERROR",
                            "error": str(error),
                            "updated_at": utc_now(),
                        },
                    )
                    if test_mode:
                        processed_in_test = True

                if test_mode and processed_in_test:
                    logger.warning("Modo de teste ativado. Encerrando apos a primeira tarefa.")
                    break

                await self._safe_delay(
                    "cooldown entre grupos",
                    base=config.GROUP_COOLDOWN_SECONDS,
                    jitter=2.0,
                )
        finally:
            await self.sub_master.disconnect()
            await self.master.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    pipeline = GroupPipeline()
    asyncio.run(pipeline.run(test_mode=args.test))
