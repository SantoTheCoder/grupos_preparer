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
)
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import ChatAdminRights, InputChatUploadedPhoto, InputPhoneContact

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


class GroupPipeline:
    def __init__(self):
        master_session = os.path.join(SESSION_DIR, "user_account.session")
        self.master = TelegramClient(
            master_session,
            config.API_ID,
            config.API_HASH,
            device_model="Desktop Windows",
            flood_sleep_threshold=0,
        )
        self.persistence = PersistenceManager()
        self.accounts = self.persistence.load_accounts()
        self.seed_queue = self.persistence.load_seed_queue()
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

    async def _connect_master(self):
        await self.master.connect()
        if not await self.master.is_user_authorized():
            await self.master.start(phone=config.PHONE)
        logger.info("Master conectado com sucesso.")

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
        owner = task.get("owner")
        phone = task.get("phone")

        for account in self.accounts:
            if phone and account.get("phone") == phone:
                return account
            if owner and account.get("name") == owner:
                return account

        return None

    def _read_text_file(self, path: str) -> str:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as file_obj:
            return file_obj.read().strip()

    async def _wait_flood(self, error: FloodWaitError, context: str):
        logger.warning("FloodWait em %s. Aguardando %ss.", context, error.seconds)
        await asyncio.sleep(error.seconds + 2)

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

        return entity

    async def _invite_and_promote_user(self, drone: TelegramClient, entity, user_ref, rank: str):
        try:
            await drone(InviteToChannelRequest(entity, [user_ref]))
        except Exception as error:
            if "already" not in str(error).lower():
                raise

        await drone(
            EditAdminRequest(
                channel=entity,
                user_id=user_ref,
                admin_rights=self.admin_rights,
                rank=rank,
            )
        )

    async def _invite_bot(self, drone: TelegramClient, entity, bot_username: str, rank: str):
        bot_entity = await drone.get_input_entity(bot_username)
        await self._invite_and_promote_user(drone, entity, bot_entity, rank)
        return bot_entity

    async def _extract_group_link(self, client: TelegramClient, entity) -> str:
        try:
            invite = await client(ExportChatInviteRequest(peer=entity))
            return invite.link
        except Exception:
            return ""

    async def _post_and_pin(self, group_id: int):
        text = self._read_text_file(config.pinned_message_file)
        if not text:
            raise RuntimeError("Texto fixado nao encontrado.")

        try:
            target = await self.master.get_entity(group_id)
        except Exception:
            await self.master.get_dialogs(limit=50)
            target = await self.master.get_entity(group_id)

        if os.path.exists(config.banner_file):
            try:
                message = await self.master.send_file(
                    target,
                    config.banner_file,
                    caption=text,
                    parse_mode="html",
                )
            except Exception:
                await self.master.send_file(target, config.banner_file)
                message = await self.master.send_message(target, text, parse_mode="html")
        else:
            message = await self.master.send_message(target, text, parse_mode="html")

        await self.master.pin_message(target, message.id, notify=True)
        return message.id

    async def _generate_gift_code(self) -> str:
        await self.master.send_message(config.GIFT_BOT_USERNAME, f"/gift {config.GIFT_VALUE}")
        await asyncio.sleep(2)

        async for message in self.master.iter_messages(config.GIFT_BOT_USERNAME, limit=5):
            if message.out:
                continue

            text = message.text or ""
            match = re.search(r"Codigo:\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
            if not match:
                match = re.search(r"Código:\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
            if match:
                return match.group(1)

        raise RuntimeError("Nao foi possivel extrair o codigo do gift.")

    async def _redeem_gift(self, group_id: int, gift_code: str):
        target = await self.master.get_entity(group_id)
        await self.master.send_message(target, f"/resgatar_gift {gift_code}")

    async def _update_gift_state(self, record: dict, gift_code: str):
        state = self.persistence.load_gift_state()
        group_key = str(record["group_id"])
        timestamp = utc_now()

        state.setdefault("groups", {})[group_key] = {
            "owner": record.get("owner", ""),
            "phone": record.get("phone", ""),
            "code": gift_code,
            "status": "DONE",
            "done_at": timestamp,
            "generated_at": timestamp,
        }
        state.setdefault("generated_codes", {})[gift_code] = {
            "group_id": record["group_id"],
            "owner": record.get("owner", ""),
            "phone": record.get("phone", ""),
            "generated_at": timestamp,
            "status": "DONE",
            "done_at": timestamp,
        }
        self.persistence.save_gift_state(state)

    def _save_task_status(self, index: int, updates: dict):
        self.seed_queue[index] = {**self.seed_queue[index], **updates}
        self.persistence.save_seed_queue(self.seed_queue)

    async def _process_task(self, index: int, task: dict):
        if task.get("status") == "READY":
            return

        account = self._resolve_drone_account(task)
        if not account:
            raise RuntimeError(f"Drone nao encontrado para tarefa: {task}")

        drone = await self._connect_drone(account)
        if drone is None:
            raise RuntimeError(f"Sessao do drone indisponivel: {account.get('phone')}")

        try:
            logger.info("Criando grupo [%s] pelo drone [%s].", task["group_name"], account.get("name"))

            await self._ensure_contact(drone, config.PHONE, "Master")
            await self._ensure_contact(self.master, account["phone"], account.get("name", "Drone"))

            entity = await self._create_group(drone, task)
            master_entity = await drone.get_input_entity(config.PHONE)

            await self._invite_and_promote_user(drone, entity, master_entity, "Master")
            await self._invite_bot(drone, entity, config.FISCAL_BOT_USERNAME, "Fiscal")
            await self._invite_bot(drone, entity, config.GIFT_BOT_USERNAME, "Gift")

            group_id = utils.get_peer_id(entity)
            invite_link = await self._extract_group_link(drone, entity)
            record = {
                "owner": account.get("name", ""),
                "phone": account.get("phone", ""),
                "internal_code": task.get("internal_code", ""),
                "group_name": task["group_name"],
                "group_id": group_id,
                "invite_link": invite_link,
                "master_added": True,
                "fiscal_bot_added": True,
                "gift_bot_added": True,
                "status": "DRONE_READY",
                "updated_at": utc_now(),
            }
            self.persistence.upsert_group_record(record)

            pinned_message_id = await self._post_and_pin(group_id)
            gift_code = await self._generate_gift_code()
            await self._redeem_gift(group_id, gift_code)

            final_record = {
                **record,
                "pinned_message_id": pinned_message_id,
                "gift_code": gift_code,
                "status": "READY",
                "updated_at": utc_now(),
            }
            self.persistence.upsert_group_record(final_record)
            await self._update_gift_state(final_record, gift_code)
            self._save_task_status(
                index,
                {
                    "status": "READY",
                    "group_id": group_id,
                    "invite_link": invite_link,
                    "updated_at": utc_now(),
                },
            )
            logger.info("Grupo [%s] concluido no novo fluxo.", task["group_name"])
        finally:
            await drone.disconnect()

    async def run(self, test_mode: bool = False):
        if not self.seed_queue:
            logger.warning("Fila de grupos vazia. Preencha data/group_seed_queue.json.")
            return

        await self._connect_master()

        try:
            for index, task in enumerate(self.seed_queue):
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
        finally:
            await self.master.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    pipeline = GroupPipeline()
    asyncio.run(pipeline.run(test_mode=args.test))
