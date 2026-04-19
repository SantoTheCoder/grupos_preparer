import asyncio
import os
import sys

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.errors.rpcerrorlist import FloodWaitError, PhoneCodeEmptyError, PhoneCodeExpiredError, PhoneCodeInvalidError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import telethon.network.mtprotostate

from core.settings import config, BASE_DIR, SESSION_DIR
from data.io_manager import PersistenceManager


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

telethon.network.mtprotostate.MSG_TOO_OLD_DELTA = 999999999
telethon.network.mtprotostate.MSG_TOO_NEW_DELTA = 999999999


SESSIONS_DIR = os.path.join(BASE_DIR, "user_client", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


async def authenticate_account(account: dict, position: int | None = None, total: int | None = None):
    name = account.get("name", "Drone")
    phone = account.get("phone")
    api_id = account.get("api_id")
    api_hash = account.get("api_hash")
    session_dir = account.get("session_dir", SESSIONS_DIR)
    session_name = account.get("session_name") or phone
    role_label = account.get("role_label", "DRONE")
    prefix = f"[{position}/{total}] " if position and total else ""
    max_code_attempts = 3

    if not phone or not api_id or not api_hash:
        print(f"{prefix}⚠️ Conta ignorada por faltar phone/api_id/api_hash: {name}", flush=True)
        return

    os.makedirs(session_dir, exist_ok=True)
    session_path = os.path.join(session_dir, f"{session_name}.session")
    print(f"{prefix}🔎 Preparando [{name}] em {session_path}", flush=True)
    client = TelegramClient(session_path, api_id, api_hash)
    print(f"{prefix}🔌 Conectando [{name}]...", flush=True)
    await client.connect()

    try:
        print(f"{prefix}🧪 Verificando autorização de [{name}]...", flush=True)
        if await client.is_user_authorized():
            print(f"{prefix}✅ [{name}] já está autenticada.", flush=True)
            return

        print(f"\n=======================================================")
        print(f"👤 INICIANDO LOGIN {role_label}: {name}")
        print(f"📱 Telefone: {phone}")
        print(f"=======================================================")
        print(f"{prefix}📨 Solicitando código para [{name}]...", flush=True)

        await client.send_code_request(phone)
        print(f"{prefix}✅ Código solicitado com sucesso para [{name}].", flush=True)
        authenticated = False

        for attempt in range(1, max_code_attempts + 1):
            code = input(
                f"💬 Digite o CÓDIGO recebido para {name} "
                f"(tentativa {attempt}/{max_code_attempts}): "
            ).strip()

            if not code:
                remaining = max_code_attempts - attempt
                if remaining > 0:
                    print(
                        f"{prefix}⚠️ Código vazio para {name}. Restam {remaining} tentativa(s).",
                        flush=True,
                    )
                    continue
                print(f"{prefix}⚠️ Limite de tentativas atingido para {name}.", flush=True)
                return

            try:
                print(f"{prefix}🔐 Validando código de [{name}]...", flush=True)
                await client.sign_in(phone, code)
                authenticated = True
                break
            except SessionPasswordNeededError:
                password = input(f"🔒 Conta {name} tem 2FA. Digite a senha: ").strip()
                print(f"{prefix}🔐 Validando senha 2FA de [{name}]...", flush=True)
                await client.sign_in(password=password)
                authenticated = True
                break
            except PhoneCodeEmptyError:
                remaining = max_code_attempts - attempt
                if remaining > 0:
                    print(
                        f"{prefix}⚠️ Código vazio para {name}. Restam {remaining} tentativa(s).",
                        flush=True,
                    )
                    continue
                print(f"{prefix}⚠️ Limite de tentativas atingido para {name}.", flush=True)
                return
            except PhoneCodeInvalidError:
                remaining = max_code_attempts - attempt
                if remaining > 0:
                    print(
                        f"{prefix}⚠️ Código inválido para {name}. Restam {remaining} tentativa(s).",
                        flush=True,
                    )
                    continue
                print(f"{prefix}⚠️ Limite de tentativas atingido para {name}.", flush=True)
                return
            except PhoneCodeExpiredError:
                remaining = max_code_attempts - attempt
                if remaining > 0:
                    print(
                        f"{prefix}⚠️ Código expirado para {name}. Solicitando um novo código...",
                        flush=True,
                    )
                    await client.send_code_request(phone)
                    print(f"{prefix}✅ Novo código solicitado para [{name}].", flush=True)
                    continue
                print(f"{prefix}⚠️ Limite de tentativas atingido para {name}.", flush=True)
                return
            except FloodWaitError as error:
                print(f"{prefix}⏳ Telegram aplicou FloodWait em {name}: aguarde {error.seconds}s antes de tentar de novo.", flush=True)
                return

        if not authenticated:
            return

        print(f"{prefix}🎉 SUCESSO! A conta de {name} foi autenticada.", flush=True)
    except FloodWaitError as error:
        print(f"{prefix}⏳ FloodWait ao solicitar código para {name}: aguarde {error.seconds}s antes de tentar novamente.", flush=True)
    except Exception as error:
        print(f"{prefix}❌ Erro inesperado em [{name}]: {error}", flush=True)
    finally:
        print(f"{prefix}🔌 Encerrando sessão local de [{name}].", flush=True)
        await client.disconnect()


async def main():
    persistence = PersistenceManager()
    accounts = persistence.load_accounts()

    print("🛡️ AUTENTICAÇÃO DE DRONES")
    print("--------------------------")
    print(f"Master fixo mantido pela sessão raiz: {config.PHONE}")

    if config.SUB_MASTER_PHONE and config.SUB_MASTER_API_ID and config.SUB_MASTER_API_HASH:
        await authenticate_account(
            {
                "name": config.SUB_MASTER_NAME,
                "phone": config.SUB_MASTER_PHONE,
                "api_id": config.SUB_MASTER_API_ID,
                "api_hash": config.SUB_MASTER_API_HASH,
                "session_dir": SESSION_DIR,
                "session_name": config.SUB_MASTER_SESSION_NAME,
                "role_label": "SUB MASTER",
            },
            position=1,
            total=len(accounts) + 1,
        )

    if not accounts:
        print("⚠️ Nenhum drone configurado em data/accounts.json.")
        return

    offset = 1 if config.SUB_MASTER_PHONE and config.SUB_MASTER_API_ID and config.SUB_MASTER_API_HASH else 0
    total_accounts = len(accounts) + offset
    for index, account in enumerate(accounts, start=1 + offset):
        await authenticate_account(account, position=index, total=total_accounts)

    print("\n✅ Todas as contas drone foram processadas.")
    print(f"📁 Sessões dos drones em: {SESSIONS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
