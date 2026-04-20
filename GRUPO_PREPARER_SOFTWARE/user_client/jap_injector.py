import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime

import aiohttp

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.settings import config
from data.io_manager import PersistenceManager

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("JAP_INJECTOR")

JAP_API_KEY = "d8226d3452cff23a39636899e8e3e48b"
JAP_API_URL = "https://justanotherpanel.com/api/v2"
SERVICE_ID = 8092
QUANTITY = 7000

async def dispatch_jap_order(session, link):
    payload = {
        "key": JAP_API_KEY,
        "action": "add",
        "service": SERVICE_ID,
        "link": link,
        "quantity": QUANTITY
    }
    
    async with session.post(JAP_API_URL, data=payload) as response:
        if response.status == 200:
            try:
                data = await response.json()
                return data
            except Exception as e:
                text = await response.text()
                logger.error("Falha ao fazer parse do JSON: %s. Resposta bruta: %s", e, text)
                return {"error": "JSON Decode Error"}
        else:
            text = await response.text()
            logger.error("Erro HTTP %s: %s", response.status, text)
            return {"error": f"HTTP {response.status}"}

async def main():
    persistence = PersistenceManager()
    groups = persistence.load_groups()
    
    if not groups:
        logger.error("Nenhum grupo encontrado em groups.json")
        return

    modifications = False
    
    async with aiohttp.ClientSession() as session:
        for index, record in enumerate(groups):
            node_name = record.get("node_operacional", "")
            match = re.search(r'bot_(\d+)', node_name)
            if not match:
                continue
                
            bot_number = int(match.group(1))
            
            # Filtro da Frota Alvo
            if not (31 <= bot_number <= 65):
                continue
                
            # Idempotencia: Verificar se ja foi injetado (protege o bot_031_novo testado)
            if record.get("jap_order_id"):
                logger.info("PULANDO: O %s ja possui um pedido ativo no JAP (ID: %s).", node_name, record.get("jap_order_id"))
                continue
                
            link = record.get("link") or record.get("invite_link") or record.get("group_link")
            if not link or link == "None":
                logger.error("O grupo %s nao possui um Link de Convite valido no JSON.", node_name)
                continue
                
            logger.info("Preparando injeçao de %s membros para %s (Link: %s)...", QUANTITY, node_name, link)
            
            # Disparo para a API JAP
            result = await dispatch_jap_order(session, link)
            
            if "order" in result:
                order_id = result["order"]
                logger.info("✅ SUCESSO! Pedido JAP criado. ID do Pedido: %s", order_id)
                
                # Persistencia iterativa de Metadados
                record["jap_order_id"] = order_id
                record["jap_order_date"] = datetime.now().isoformat()
                record["jap_order_quantity"] = QUANTITY
                record["jap_order_service"] = SERVICE_ID
                
                groups[index] = record
                modifications = True
                persistence.save_groups(groups) # Salva na hora para evitar perdas
            elif "error" in result:
                logger.error("❌ ERRO do Painel JAP para %s: %s", node_name, result["error"])
                # Se der saldo insuficiente ou erro grave, abortar tudo na hora
                if "balance" in str(result["error"]).lower() or "fund" in str(result["error"]).lower():
                    logger.critical("🛑 SALDO INSUFICIENTE DETECTADO! ABORTANDO ROTEIRO PARA PROTEGER DINHEIRO E EVITAR BLOQUEIO NA API.")
                    break
            else:
                logger.error("Resposta desconhecida do Painel JAP para %s: %s", node_name, result)
                
            # Atraso anti-spam na API JAP
            await asyncio.sleep(1)

    logger.info("🏁 Varredura da Frota JAP concluída.")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
