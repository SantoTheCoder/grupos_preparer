import asyncio
import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.functions.channels import EditTitleRequest

from core.settings import BASE_DIR, config
from data.io_manager import PersistenceManager

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("RENAME_OPS")

DRONE_SESSION_DIR = os.path.join(BASE_DIR, "user_client", "sessions")
LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

# Mapeamento Unicode: Mathematical Sans-Serif Bold
UNICODE_MAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
)

async def correct_group_names():
    persistence = PersistenceManager()
    groups = persistence.load_groups()
    
    if not groups:
        logger.error("groups.json vazio ou nao encontrado.")
        return

    modifications_made = False

    for index, record in enumerate(groups):
        node_name = record.get("node_operacional", "")
        match = re.search(r'bot_(\d+)', node_name)
        if not match:
            continue
            
        bot_number = int(match.group(1))
        
        # Filtro cirurgico: processar apenas do 31 ao 65
        if not (31 <= bot_number <= 65):
            continue

        # Algoritmo de mapeamento O(1)
        letter_index = (bot_number - 1) // 10
        unit_value = ((bot_number - 1) % 10) + 1
        
        target_letter = LETTERS[letter_index]
        new_code_ascii = f"{target_letter}{unit_value:02d}"
        
        # Aplica tipografia unicode especial
        new_code_styled = new_code_ascii.translate(UNICODE_MAP)
        
        # Internal code can remain ASCII or styled. Let's make it ASCII for backend matching, 
        # but the old script made internal_code styled or ascii? Wait, the user's groups.json 
        # had "internal_code": "C11" in ASCII. The title had the styled one. 
        # So we update internal_code as ASCII, group_name as STYLED.
        
        old_name = record.get("group_name", "")
        new_name = f"🕵️‍♂️ 𝗩Λ𝗥𝗥𝗘𝗗𝗨𝗥Λ 𝗚𝗥Λ́𝗧𝗜𝗦 ［#{new_code_styled}］ ⚡️ 〘 𝗜Λ 𝗗𝗘𝗧𝗘𝗧𝗜𝗩𝗘 〙"
        
        # Evita chamadas duplicadas se o nome ja estiver perfeito
        if old_name == new_name:
            logger.info("Ignorando [%s]: Titulo ja esta com a tipografia correta.", node_name)
            continue
        
        group_id = record.get("group_id")
        phone = record.get("phone")
        
        if not group_id or not phone:
            logger.warning("Faltam dados criticos (group_id/phone) no nó %s. Pulando.", node_name)
            continue
            
        session_path = os.path.join(DRONE_SESSION_DIR, f"{phone}.session")
        if not os.path.exists(session_path):
            logger.warning("Sessao nao encontrada para o telefone %s. Pulando.", phone)
            continue

        # Intervencao de Rede
        client = TelegramClient(session_path, config.API_ID, config.API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("Sessao desautorizada para %s", phone)
            await client.disconnect()
            continue

        try:
            entity = await client.get_entity(group_id)
            logger.info("Executando rename via rede: [%s] -> %s", node_name, new_name)
            
            await client(EditTitleRequest(channel=entity, title=new_name))
            
            # Atualiza estado de memoria
            record["internal_code"] = new_code_ascii
            record["group_name"] = new_name
            groups[index] = record
            persistence.save_groups(groups)
            modifications_made = True
            
            logger.info("✅ Sucesso para o nó %s. Titulo aplicado com Unicode Sans-Serif Bold.", node_name)
            
        except FloodWaitError as e:
            logger.error("🛑 Bloqueio termico (FloodWait) no telefone %s. Aguarde %s seg.", phone, e.seconds)
            await asyncio.sleep(3) # Atraso basal apos erro
        except Exception as e:
            if "wasn't modified" in str(e).lower() or "not modified" in str(e).lower():
                logger.info("⚠️ Nó %s já estava com o nome correto na rede. Sincronizando JSON...", node_name)
                record["internal_code"] = new_code_ascii
                record["group_name"] = new_name
                groups[index] = record
                persistence.save_groups(groups)
                modifications_made = True
            else:
                logger.error("Erro critico ao renomear nó %s: %s", node_name, e)
        finally:
            await client.disconnect()

        await asyncio.sleep(0.5) # Acelerado conforme demanda (risco termico aceito)

    if modifications_made:
        persistence.save_groups(groups)
        logger.info("Persistencia em groups.json concluida com integridade total.")
    else:
        logger.info("Nenhuma modificacao foi necessaria ou executada.")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(correct_group_names())
