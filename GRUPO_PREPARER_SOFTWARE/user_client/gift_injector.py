import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError

from core.settings import SESSION_DIR, config
from data.io_manager import PersistenceManager


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("GIFT_MASTER")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GiftInjector:
    def __init__(self):
        master_session = os.path.join(SESSION_DIR, "user_account.session")
        self.master = TelegramClient(master_session, config.API_ID, config.API_HASH, flood_sleep_threshold=0)
        self.persistence = PersistenceManager()

    async def _generate_gift_code(self) -> str:
        await self.master.send_message(config.GIFT_BOT_USERNAME, f"/gift {config.GIFT_VALUE}")
        await asyncio.sleep(2)

        async for message in self.master.iter_messages(config.GIFT_BOT_USERNAME, limit=5):
            if message.out:
                continue

            text = message.text or ""
            match = re.search(r"SYNTAX-[A-Z0-9]+", text, re.IGNORECASE)
            if match:
                return match.group(0)

        raise RuntimeError("Nao foi possivel extrair o codigo do gift.")

    def _save_gift_state(self, record: dict, gift_code: str, redeem_message_id: int):
        next_record = {
            **record,
            "gift_code": gift_code,
            "gift_redeem_message_id": redeem_message_id,
            "status": "READY",
            "updated_at": utc_now(),
        }
        self.persistence.upsert_group_record(next_record)

    async def run(self):
        groups = self.persistence.load_groups()
        if not groups:
            logger.warning("Base de grupos vazia. Nada para processar.")
            return

        await self.master.connect()
        if not await self.master.is_user_authorized():
            await self.master.start(phone=config.PHONE)

        try:
            for record in groups:
                group_id = record.get("group_id")
                if not group_id:
                    continue

                try:
                    gift_code = await self._generate_gift_code()
                    sent = await self.master.send_message(group_id, f"/resgatar_gift {gift_code}")
                    self._save_gift_state(record, gift_code, sent.id)
                    logger.info("Gift reenviado para [%s].", record.get("group_name", group_id))
                    await asyncio.sleep(2)
                except FloodWaitError as error:
                    logger.warning("FloodWait ao reenviar gift. Aguardando %ss.", error.seconds)
                    await asyncio.sleep(error.seconds + 2)
                except Exception as error:
                    logger.error("Falha ao reenviar gift para [%s]: %s", record.get("group_name", group_id), error)
        finally:
            await self.master.disconnect()


if __name__ == "__main__":
    injector = GiftInjector()
    asyncio.run(injector.run())
