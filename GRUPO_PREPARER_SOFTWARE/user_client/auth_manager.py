import os
import sys
import json
import asyncio
from getpass import getpass
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# Certifique-se de estar rodando UTF-8 no Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Monkey-Patching Brutal no MTProto (Bug de TimeSync do Windows -> Telegram)
import telethon.network.mtprotostate
telethon.network.mtprotostate.MSG_TOO_OLD_DELTA = 999999999
telethon.network.mtprotostate.MSG_TOO_NEW_DELTA = 999999999

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
SESSIONS_DIR = os.path.join(BASE_DIR, 'sessions')

os.makedirs(SESSIONS_DIR, exist_ok=True)

MAPPING_FILE = os.path.join(DATA_DIR, 'accounts_mapping.json')

async def authenticate_account(account):
    name = account.get('name')
    phone = account.get('phone')
    api_id = account.get('api_id')
    api_hash = account.get('api_hash')

    session_path = os.path.join(SESSIONS_DIR, f"{phone}.session")

    # Verifica se a sessão já existe e tem conexão válida
    if os.path.exists(session_path):
        client = TelegramClient(session_path, api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            print(f"✅ [{name}] Conta já estavá logada. Ignorando...")
            await client.disconnect()
            return
        else:
            print(f"⚠️ [{name}] Arquivo de sessão corrompido ou deslogado. Refazendo login...")
            await client.disconnect()
            os.remove(session_path)

    print(f"\n=======================================================")
    print(f"👤 INICIANDO LOGIN: {name}")
    print(f"📱 Telefone: {phone}")
    print(f"=======================================================")
    
    choice = input("Pressione [ENTER] para enviar o SMS ou digite 'p' para pular: ")
    if choice.strip().lower() == 'p':
        print(f"⏭️ Pulando a conta {name}...\n")
        return

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()

    try:
        # Pede o envio do código SMS
        print("📨 Enviando código via Telegram...")
        # Telethon faz o envio automático quando chamamos send_code_request se não autorizado
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            
            code = input(f"💬 Digite o CÓDIGO recebido no Telegram do(a) {name}: ")
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                # Caso a conta tenha verificação em Duas Etapas (2FA) = Senha Nuvem
                password = input(f"🔒 Essa conta tem autenticação 2FA! Digite a senha da nuvem: ")
                await client.sign_in(password=password)
            
        print(f"🎉 SUCESSO! A conta de {name} foi blindada e logada.")
    except Exception as e:
        print(f"❌ ERRO durante o login de {name}: {e}")
    finally:
        await client.disconnect()


async def main():
    print("🛡️ MÓDULO DE AUTENTICAÇÃO EM LOTE - TELETHON")
    print("---------------------------------------------")
    
    if not os.path.exists(MAPPING_FILE):
        print(f"❌ Erro crítico: O arquivo {MAPPING_FILE} não foi encontrado.")
        return

    with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
        accounts = json.load(f)

    print(f"📥 Base de contas carregada: {len(accounts)} cadastradas no JSON.\n")
    
    for acc in accounts:
        await authenticate_account(acc)
        
    print("\n✅ TODAS AS CONTAS PROCESSADAS.")
    print(f"📁 Seus arquivos .session estão seguros na pasta: {SESSIONS_DIR}")

if __name__ == '__main__':
    asyncio.run(main())
