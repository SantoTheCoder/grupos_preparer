import asyncio
import logging
import os
import json
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger("ZELADOR.Broadcaster")

# Caminhos absolutos retro-compatíveis com a árvore da Fase 3
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def get_env_bool(key: str, default: bool = True) -> bool:
    val = os.getenv(key, "")
    return val.lower() in ("true", "1", "yes") if val else default

async def cron_broadcaster(bot: Bot):
    """
    Subrotina injetada no Loop Assíncrono do Vigia.
    Atira o Marketing e deleta o rastro visual anterior automaticamente.
    """
    daily_msg_path = os.path.join(DATA_DIR, 'daily_message.txt')
    daily_banner_path = os.path.join(BASE_DIR, 'daily_banner.png')
    history_path = os.path.join(DATA_DIR, 'broadcast_history.json')
    prod_state_path = os.path.join(DATA_DIR, 'production_groups.json')
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if not os.path.exists(daily_msg_path):
        with open(daily_msg_path, 'w', encoding='utf-8') as f:
            f.write("Mensagem diária padrão. Substitua arquivo daily_message.txt.")
            
    first_run = True
    while True:
        try:
            interval_str = os.getenv("BROADCAST_INTERVAL_MINUTES", "120")
            delay_seconds = int(interval_str) * 60
        except ValueError:
            delay_seconds = 7200 # 2 Horas padrão em caso de erro em string
            
        if not first_run:
            logger.info(f"⏳ [ZELADOR] Aguardando {delay_seconds/60}min para disparar matriz comercial...")
            await asyncio.sleep(delay_seconds)
            
        first_run = False
        
        logger.info("🚀 [ZELADOR] Acordando módulo! Realizando disparos em massa...")
        
        # 1. Obter snapshot dos grupos da Fase 3
        groups = []
        if os.path.exists(prod_state_path):
            try:
                with open(prod_state_path, 'r', encoding='utf-8') as f:
                    groups = json.load(f)
            except Exception as e:
                logger.error(f"Erro ao ler production_groups.json: {e}")
                
        if not groups:
            logger.warning("Nenhum alvo encontrado no JSON matriz de Produção. Loop finalizado.")
            continue
            
        with open(daily_msg_path, 'r', encoding='utf-8') as f:
            daily_text = f.read()
            
        # 2. Resgatar Cache Tático Visual (Anti-Flood ID Tracker)
        history = {}
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                pass
                
        # 3. Fabricar Botão Inline (se configurado)
        markup = None
        btn_text = os.getenv("BUTTON_TEXT", "")
        btn_url = os.getenv("BUTTON_URL", "")
        if btn_text and btn_url:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn_text, url=btn_url)]
            ])
            
        delete_old = get_env_bool("DELETE_OLD_BROADCAST", True)
        
        for group in groups:
            chat_id = group["ID"]
            chat_id_str = str(chat_id)
            
            # --- TIER 1: A Lixeira Invisível ---
            if delete_old and chat_id_str in history:
                old_msg_id = history[chat_id_str]
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
                    logger.debug(f"🧹 Banner Anterior Apagado em [{group.get('NOME', chat_id)}].")
                except TelegramAPIError:
                    pass # Normal se o post já foi deletado por outro robô ou admin.
                    
            # --- TIER 2: O Novo Impacto Visual ---
            try:
                sent_msg = None
                if os.path.exists(daily_banner_path):
                    photo = FSInputFile(daily_banner_path)
                    sent_msg = await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=daily_text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
                else:
                    sent_msg = await bot.send_message(
                        chat_id=chat_id,
                        text=daily_text,
                        reply_markup=markup,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                
                # Consolidar rastro final
                if sent_msg:
                    history[chat_id_str] = sent_msg.message_id
                    logger.info(f"✅ Disparo Sucesso: [{group.get('NOME', chat_id)}]")
                    
            except TelegramAPIError as e:
                logger.error(f"❌ Falha Aiogram em [{group.get('NOME', chat_id)}]: {e}")
                
            # Jitter Micro-Intervalado de envio (Protege sua API KEY)
            await asyncio.sleep(2)
            
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f)
            
        logger.info("🏁 [ZELADOR] Loop de marketing concluído!")
