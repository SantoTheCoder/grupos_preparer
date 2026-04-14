import asyncio
import logging
import os
import json
from telethon import Button
from core.settings import config, BASE_DIR, DATA_DIR
from data.io_manager import PersistenceManager

logger = logging.getLogger("ZELADOR.Broadcaster")

async def cron_broadcaster(client):
    """
    Motor Massivo de Disparos. Inicia assim que o bot conecta e fica em loop infinito iterativo.
    """
    persistence = PersistenceManager()
    
    daily_msg_path = os.path.join(DATA_DIR, 'daily_message.txt')
    daily_banner_path = os.path.join(BASE_DIR, 'daily_banner.png')
    history_path = os.path.join(DATA_DIR, 'broadcast_history.json')
    
    # Criar placeholders se não existirem
    if not os.path.exists(daily_msg_path):
        with open(daily_msg_path, 'w', encoding='utf-8') as f:
            f.write("Esta é a sua mensagem diária. Você pode alterá-la livremente.")
            
    while True:
        # Repouso estipulado pelo arquiteto (.env)
        delay_seconds = config.BROADCAST_INTERVAL_MINUTES * 60
        logger.info(f"⏳ Cron-Job Dormindo por {config.BROADCAST_INTERVAL_MINUTES} minutos antes do próximo disparo...")
        await asyncio.sleep(delay_seconds)
        
        logger.info("🚀 Acordando! Iniciando varredura e disparo de Banners...")
        
        groups = persistence.load_production_state()
        if not groups:
            logger.warning("Nenhum grupo encontrado em production_groups.json. Abortando ciclo.")
            continue
            
        with open(daily_msg_path, 'r', encoding='utf-8') as f:
            daily_text = f.read()
            
        # Carregar histórico das mensagens antigas enviadas (Deleção de Anti-Spam)
        history = {}
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                pass
                
        # Construir o Botão Transparente Clicável
        botoes = None
        if config.BUTTON_TEXT and config.BUTTON_URL:
            botoes = [[Button.url(config.BUTTON_TEXT, config.BUTTON_URL)]]
            
        for group in groups:
            chat_id = group["ID"]
            chat_id_str = str(chat_id)
            
            # --- FASE 1: Deleção Higiênica do Banner Antigo ---
            if config.DELETE_OLD_BROADCAST and chat_id_str in history:
                old_msg_id = history[chat_id_str]
                try:
                    await client.delete_messages(chat_id, old_msg_id)
                    logger.debug(f"🧹 Banner Antigo deletado em [{group['NOME']}].")
                except Exception as e:
                    logger.warning(f"Não foi possível apagar banner estrito antigo no chat {chat_id}: {e}")
                    
            # --- FASE 2: Injeção do Novo Banner ---
            try:
                sent_msg = None
                if os.path.exists(daily_banner_path):
                    # Com Foto
                    sent_msg = await client.send_file(
                        chat_id, 
                        daily_banner_path, 
                        caption=daily_text, 
                        buttons=botoes,
                        parse_mode='html'
                    )
                else:
                    # Sem Foto
                    sent_msg = await client.send_message(
                        chat_id, 
                        daily_text, 
                        buttons=botoes,
                        parse_mode='html'
                    )
                
                # Registra o tiro bem sucedido no histórico
                if sent_msg:
                    history[chat_id_str] = sent_msg.id
                    logger.info(f"✅ Disparo Concluído em: [{group['NOME']}]")
                    
            except Exception as e:
                logger.error(f"❌ Falha de Disparo em [{group['NOME']}]: {e}")
                
            # Rate-limit dinâmico (Proteção antispam da API do Telegram)
            await asyncio.sleep(2)
            
        # Salva o Tracker de deleção limpa (Checkpoint do Array)
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f)
            
        logger.info("🏁 Ciclo de Broadcast e Limpeza finalizado com sucesso!")
