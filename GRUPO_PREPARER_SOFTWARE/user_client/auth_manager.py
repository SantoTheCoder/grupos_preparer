import asyncio
import os
import sys

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import telethon.network.mtprotostate

from core.settings import config, BASE_DIR
from data.io_manager import PersistenceManager


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

telethon.network.mtprotostate.MSG_TOO_OLD_DELTA = 999999999
telethon.network.mtprotostate.MSG_TOO_NEW_DELTA = 999999999


SESSIONS_DIR = os.path.join(BASE_DIR, "user_client", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


async def authenticate_account(account: dict):
    name = account.get("name", "Drone")
    phone = account.get("phone")
    api_id = account.get("api_id")
    api_hash = account.get("api_hash")

    if not phone or not api_id or not api_hash:
        print(f"⚠️ Conta ignorada por faltar phone/api_id/api_hash: {name}")
        return

    session_path = os.path.join(SESSIONS_DIR, f"{phone}.session")
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()

    try:
        if await client.is_user_authorized():
            print(f"✅ [{name}] já está autenticada.")
            return

        print(f"\n=======================================================")
        print(f"👤 INICIANDO LOGIN DRONE: {name}")
        print(f"📱 Telefone: {phone}")
        print(f"=======================================================")

        await client.send_code_request(phone)
        code = input(f"💬 Digite o CÓDIGO recebido para {name}: ")

        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input(f"🔒 Conta {name} tem 2FA. Digite a senha: ")
            await client.sign_in(password=password)

        print(f"🎉 SUCESSO! A conta de {name} foi autenticada.")
    finally:
        await client.disconnect()


async def main():
    persistence = PersistenceManager()
    accounts = persistence.load_accounts()

    print("🛡️ AUTENTICAÇÃO DE DRONES")
    print("--------------------------")
    print(f"Master fixo mantido pela sessão raiz: {config.PHONE}")

    if not accounts:
        print("⚠️ Nenhum drone configurado em data/accounts_mapping.json.")
        return

    for account in accounts:
        await authenticate_account(account)

    print("\n✅ Todas as contas drone foram processadas.")
    print(f"📁 Sessões dos drones em: {SESSIONS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
