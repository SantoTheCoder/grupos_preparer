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
    InviteToChannelRequest,
    ToggleSlowModeRequest,
)
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.functions.messages import EditChatDefaultBannedRightsRequest, ExportChatInviteRequest
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
        )
        self.sub_master_admin_rights = ChatAdminRights(
            change_info=True,
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=True,
            add_admins=True,
            anonymous=True,
            manage_call=True,
            manage_topics=True,
        )

    async def _connect_master(self):
        await self.master.connect()
        if not await self.master.is_user_authorized():
            await self.master.start(phone=config.PHONE)
        logger.info("Master conectado com sucesso.")

    async def _connect_sub_master(self):
        if not config.SUB_MASTER_PHONE:
            raise RuntimeError("SUB_MASTER_PHONE nao configurado no .env.")
        if not config.SUB_MASTER_API_ID or not config.SUB_MASTER_API_HASH:
            raise RuntimeError("SUB_MASTER_API_ID/SUB_MASTER_API_HASH nao configurados no .env.")

        if not os.path.exists(config.sub_master_session_file):
            raise RuntimeError(f"Sessao do sub master nao encontrada: {config.sub_master_session_file}")

        await self.sub_master.connect()
        if not await self.sub_master.is_user_authorized():
            await self.sub_master.disconnect()
            raise RuntimeError("Sessao do sub master nao esta autorizada.")
        logger.info("Sub master conectado com sucesso.")

    async def _connect_drone(self, account: dict) -> TelegramClient | None:
        phone = account.get("phone")
        api_id = account.get("api_id")
        api_hash = account.get("api_hash")
        session_path = os.path.join(DRONE_SESSION_DIR, f"{phone}.session")

        if not os.path.exists(session_path):
            logger.error("Sessao do drone nao encontrada: %s", phone)
            return None

        client = TelegramClient(session_path, api_id, api_hash, flood_sleep_threshold=0)
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("Sessao do drone nao esta autorizada: %s", phone)
            await client.disconnect()
            return None

        return client

    def _resolve_drone_account(self, task: dict) -> dict | None:
        account_id = task.get("account_id")
        owner = task.get("owner")
        phone = task.get("phone")

        for account in self.accounts:
            if account_id and account.get("account_id") == account_id:
                return account
            if phone and account.get("phone") == phone:
                return account
            if owner and account.get("name") == owner:
                return account

        return None

    def _find_existing_record(self, task: dict) -> dict | None:
        group_id = task.get("group_id")
        account_id = task.get("account_id")
        owner = task.get("owner")
        internal_code = task.get("internal_code")

        for record in self.persistence.load_groups():
            if group_id and record.get("group_id") == group_id:
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

    async def _wait_flood(self, error: FloodWaitError, context: str):
        logger.warning("FloodWait em %s. Aguardando %ss.", context, error.seconds)
        await asyncio.sleep(error.seconds + 2)

    async def _safe_delay(self, reason: str, base: float | None = None, jitter: float | None = None):
        delay_base = config.ACTION_DELAY_SECONDS if base is None else base
        delay_jitter = config.ACTION_DELAY_JITTER_SECONDS if jitter is None else jitter
        total_delay = max(0.0, delay_base + random.uniform(0.0, max(0.0, delay_jitter)))
        logger.debug("Delay de seguranca (%s): %.2fs", reason, total_delay)
        await asyncio.sleep(total_delay)

    async def _ensure_contact(self, client: TelegramClient, phone: str, first_name: str):
        try:
            await client(
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
        except FloodWaitError as error:
            await self._wait_flood(error, f"importar contato {phone}")

    async def _create_group(self, drone: TelegramClient, task: dict):
        description = self._read_text_file(config.group_description_file)
        response = await drone(
            CreateChannelRequest(
                title=task["group_name"],
                about=description,
                megagroup=True,
            )
        )
        await self._safe_delay(f"criar grupo {task['group_name']}")
        created_chat = response.chats[0]
        entity = await drone.get_entity(created_chat)

        if os.path.exists(config.avatar_file):
            uploaded = await drone.upload_file(config.avatar_file)
            await drone(
                ChannelEditPhotoRequest(
                    channel=entity,
                    photo=InputChatUploadedPhoto(file=uploaded),
                )
            )
            await self._safe_delay(f"aplicar foto do grupo {task['group_name']}")

        return entity

    async def _pin_group_dialog(self, drone: TelegramClient, entity):
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
            await drone(InviteToChannelRequest(entity, [user_ref]))
            await self._safe_delay(f"adicionar participante {rank}")
        except Exception as error:
            if "already" not in str(error).lower():
                raise

        await drone(
            EditAdminRequest(
                channel=entity,
                user_id=user_ref,
                admin_rights=admin_rights or self.admin_rights,
                rank=rank,
            )
        )
        await self._safe_delay(f"promover admin {rank}")

    async def _invite_bot(self, drone: TelegramClient, entity, bot_username: str, rank: str):
        bot_entity = await drone.get_input_entity(bot_username)
        await self._invite_and_promote_user(drone, entity, bot_entity, rank)
        return bot_entity

    async def _configure_group_permissions(self, drone: TelegramClient, entity):
        allowed_members_rights = ChatBannedRights(
            until_date=None,
            send_messages=False,
            send_media=False,
            send_stickers=False,
            send_gifs=False,
            send_games=False,
            send_inline=False,
            embed_links=False,
            send_polls=False,
            change_info=True,
            invite_users=False,
            pin_messages=True,
            manage_topics=True,
            send_photos=False,
            send_videos=False,
            send_roundvideos=False,
            send_audios=False,
            send_voices=False,
            send_docs=False,
            send_plain=False,
            edit_rank=True,
        )
        await drone(EditChatDefaultBannedRightsRequest(entity, allowed_members_rights))
        await self._safe_delay("configurar permissoes padrao do grupo")
        await drone(ToggleSlowModeRequest(channel=entity, seconds=300))
        await self._safe_delay("configurar slow mode do grupo")

    async def _extract_group_link(self, client: TelegramClient, entity) -> str:
        try:
            invite = await client(ExportChatInviteRequest(peer=entity))
            return invite.link
        except Exception:
            return ""

    async def _get_master_target(self, group_id: int):
        try:
            return await self.master.get_entity(group_id)
        except Exception:
            await self.master.get_dialogs(limit=50)
            return await self.master.get_entity(group_id)

    async def _ensure_sub_master_contact_flow(self, drone: TelegramClient, account: dict):
        await self._ensure_contact(drone, config.SUB_MASTER_PHONE, config.SUB_MASTER_NAME)
        await self._ensure_contact(self.sub_master, account["phone"], account.get("name", "Drone"))

    async def _add_sub_master(self, drone: TelegramClient, entity, account: dict):
        await self._ensure_sub_master_contact_flow(drone, account)
        sub_master_entity = await drone.get_input_entity(config.SUB_MASTER_PHONE)
        await self._invite_and_promote_user(
            drone,
            entity,
            sub_master_entity,
            "Sub Master",
            admin_rights=self.sub_master_admin_rights,
        )

    async def _send_master_photo(self, target):
        if not os.path.exists(config.banner_file):
            return None
        message = await self.master.send_file(target, config.banner_file)
        await self._safe_delay("enviar foto do master")
        return message.id

    async def _send_master_text(self, target, text: str):
        message = await self.master.send_message(target, text, parse_mode="html")
        await self._safe_delay("enviar texto do master")
        return message.id

    async def _pin_master_text(self, target, message_id: int):
        await self.master.pin_message(target, message_id, notify=True)
        await self._safe_delay("fixar texto do master")

    async def _redeem_gift(self, target, gift_code: str):
        message = await self.master.send_message(target, f"/resgatar_gift {gift_code}")
        await self._safe_delay("enviar resgate do gift")
        return message.id

    async def _generate_gift_code(self) -> str:
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
                return match.group(0)

        raise RuntimeError("Nao foi possivel extrair o codigo do gift.")

    def _save_task_status(self, index: int, updates: dict):
        next_task = {**self.groups[index], **updates}
        if next_task.get("status") == "READY":
            next_task.pop("error", None)
        self.groups[index] = next_task
        self.persistence.save_groups(self.groups)

    def _persist_record(self, index: int, record: dict, task_status: str):
        record["status"] = task_status
        record["updated_at"] = utc_now()
        self.persistence.upsert_group_record(record)
        task_updates = {
            "status": task_status,
            "group_id": record["group_id"],
            "invite_link": record.get("invite_link", ""),
            "updated_at": record["updated_at"],
        }
        self._save_task_status(index, task_updates)

    async def _process_task(self, index: int, task: dict):
        if task.get("status") == "READY":
            return

        account = self._resolve_drone_account(task)
        if not account:
            raise RuntimeError(f"Drone nao encontrado para tarefa: {task}")
        account_id = account.get("account_id") or build_account_id(account.get("name", "Drone"), account.get("phone", ""))
        account["account_id"] = account_id

        drone = await self._connect_drone(account)
        if drone is None:
            raise RuntimeError(f"Sessao do drone indisponivel: {account.get('phone')}")

        try:
            existing_record = self._find_existing_record(task)

            await self._ensure_contact(drone, config.PHONE, "Master")
            await self._ensure_contact(self.master, account["phone"], account.get("name", "Drone"))

            if existing_record and existing_record.get("group_id"):
                logger.info(
                    "Retomando grupo existente [%s] para o drone [%s].",
                    existing_record.get("group_name", task["group_name"]),
                    account.get("name"),
                )
                entity = await drone.get_entity(existing_record["group_id"])
                invite_link = existing_record.get("invite_link", "")
            else:
                logger.info("Criando grupo [%s] pelo drone [%s].", task["group_name"], account.get("name"))
                entity = await self._create_group(drone, task)
                await self._pin_group_dialog(drone, entity)
                invite_link = await self._extract_group_link(drone, entity)

            master_entity = await drone.get_input_entity(config.PHONE)

            await self._invite_and_promote_user(drone, entity, master_entity, "Master")
            await self._add_sub_master(drone, entity, account)
            await self._invite_bot(drone, entity, config.FISCAL_BOT_USERNAME, "Fiscal")
            await self._invite_bot(drone, entity, config.GIFT_BOT_USERNAME, "Ia Detetive")
            await self._configure_group_permissions(drone, entity)

            group_id = utils.get_peer_id(entity)
            if not invite_link:
                invite_link = await self._extract_group_link(drone, entity)
            record = {
                **(existing_record or {}),
                "account_id": account_id,
                "owner": account.get("name", ""),
                "phone": account.get("phone", ""),
                "internal_code": task.get("internal_code", ""),
                "group_name": task["group_name"],
                "group_id": group_id,
                "invite_link": invite_link,
                "dialog_pinned": True,
                "master_added": True,
                "sub_master_added": True,
                "sub_master_admin": True,
                "sub_master_anonymous": True,
                "sub_master_name": config.SUB_MASTER_NAME,
                "sub_master_phone": config.SUB_MASTER_PHONE,
                "sub_master_rank": "Sub Master",
                "fiscal_bot_added": True,
                "gift_bot_added": True,
                "gift_bot_rank": "Ia Detetive",
                "member_permissions_configured": True,
                "slow_mode_seconds": 300,
                "created_at": (existing_record or {}).get("created_at", utc_now()),
            }
            self._persist_record(index, record, "DRONE_READY")

            target = await self._get_master_target(group_id)
            text = self._read_text_file(config.pinned_message_file)
            if not text:
                raise RuntimeError("Texto fixado nao encontrado.")

            if os.path.exists(config.banner_file) and not record.get("photo_message_id"):
                record["photo_message_id"] = await self._send_master_photo(target)
                self._persist_record(index, record, "MASTER_PHOTO_SENT")

            if not record.get("text_message_id"):
                record["text_message_id"] = await self._send_master_text(target, text)
                self._persist_record(index, record, "MASTER_TEXT_SENT")

            if not record.get("pinned_message_id"):
                await self._pin_master_text(target, record["text_message_id"])
                record["pinned_message_id"] = record["text_message_id"]
                self._persist_record(index, record, "MASTER_PINNED")

            if not record.get("gift_code"):
                record["gift_code"] = await self._generate_gift_code()
                self._persist_record(index, record, "GIFT_CREATED")

            if not record.get("gift_redeem_message_id"):
                record["gift_redeem_message_id"] = await self._redeem_gift(target, record["gift_code"])
                self._persist_record(index, record, "GIFT_SENT")

            self._persist_record(index, record, "READY")
            logger.info("Grupo [%s] concluido no novo fluxo.", task["group_name"])
        finally:
            await drone.disconnect()

    async def run(self, test_mode: bool = False):
        if not self.groups:
            logger.warning("Base de grupos vazia. Preencha data/groups.json.")
            return

        await self._connect_master()
        await self._connect_sub_master()

        try:
            for index, task in enumerate(self.groups):
                try:
                    await self._process_task(index, task)
                except FloodWaitError as error:
                    await self._wait_flood(error, task.get("group_name", "tarefa"))
                except Exception as error:
                    logger.error("Falha no grupo [%s]: %s", task.get("group_name", "SEM_NOME"), error)
                    self._save_task_status(
                        index,
                        {
                            "status": "ERROR",
                            "error": str(error),
                            "updated_at": utc_now(),
                        },
                    )

                if test_mode:
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
