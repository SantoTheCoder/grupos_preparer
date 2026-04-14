# main_vigia.py

import asyncio
import logging
import os
import platform
import re
import aiosqlite
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from aiocache import cached, Cache
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatType, MessageEntityType
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv

# --- Módulos Especializados ---
# <<< IMPLEMENTAÇÃO: INSTANT_BAN_TERMS importado para o filtro de tolerância zero.
from config import DB_FILE, COOLDOWN_PERIODS_IN_DAYS, FORBIDDEN_CONTENT_REGEX, INSTANT_BAN_TERMS
import scta_analyzer

# --- Configuração Inicial ---
if not load_dotenv():
    logging.warning("Arquivo .env não encontrado. As variáveis de ambiente devem ser definidas manualmente.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Carregamento e Validação Robusta de Variáveis de Ambiente ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID")

if not BOT_TOKEN:
    logging.critical("Erro Crítico: O BOT_TOKEN não foi encontrado no ambiente. O sistema não pode iniciar.")
    exit()

LOG_CHANNEL_ID = None
if LOG_CHANNEL_ID_STR:
    try:
        LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR)
        logging.info(f"Canal de Log configurado com sucesso para o ID: {LOG_CHANNEL_ID}.")
    except ValueError:
        logging.critical("Erro Crítico: LOG_CHANNEL_ID é inválido. Deve ser um número inteiro. O sistema não pode iniciar.")
        exit()
else:
    logging.warning("Aviso: LOG_CHANNEL_ID não está configurado. A funcionalidade de log de auditoria está desativada.")

# --- Estado Global e Constantes ---
dp = Dispatcher()
log_queue = asyncio.Queue()
ANONYMOUS_ADMIN_ID = 1087968824
EMAIL_ONLY_REGEX = re.compile(r"^\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\s*$")

# --- Módulo de Log de Auditoria Desacoplado ---
async def log_processor_task(bot: Bot):
    """
    Tarefa consumidora que processa a fila de logs e os envia ao canal de auditoria.
    """
    while True:
        try:
            log_data: Dict[str, Any] = await log_queue.get()
            original_message_escaped = (
                log_data['original_message']
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
            )
            
            user_info = f"<a href='tg://user?id={log_data['user_id']}'>{log_data['user_full_name']}</a>"
            
            log_text = (
                f"<b> L O G | Ação de Moderação </b>\n\n"
                f"<b>Usuário:</b> {user_info} (<code>{log_data['user_id']}</code>)\n"
                f"<b>Grupo:</b> {log_data['chat_title']} (<code>{log_data['chat_id']}</code>)\n\n"
                f"<b>Tipo de Violação:</b> {log_data['violation_type']}\n"
                f"<b>Ação Realizada:</b> {log_data['action_description'].split('(')[0].strip()}\n"
                f"<b>Nível da Infração:</b> {log_data.get('warn_count', 'N/A')}º aviso\n\n"
                f"<b>Conteúdo Original:</b>\n<pre><code class='language-text'>{original_message_escaped}</code></pre>"
            )

            if LOG_CHANNEL_ID:
                await bot.send_message(
                    chat_id=LOG_CHANNEL_ID,
                    text=log_text,
                    parse_mode="HTML"
                )
            log_queue.task_done()
        except TelegramBadRequest as e:
            logging.error(f"Erro ao enviar log para o canal {LOG_CHANNEL_ID}: {e}")
        except Exception as e:
            logging.error(f"Erro inesperado no processador de logs: {e}")

# --- Módulo de Banco de Dados ---
async def setup_database():
    """Cria a tabela de infrações no banco de dados, se não existir."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS infractions (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                warn_count INTEGER NOT NULL,
                last_infraction_timestamp INTEGER NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await db.commit()
        logging.info(f"Banco de dados '{DB_FILE}' verificado e pronto.")

# --- Funções de Lógica Principal e Cache ---
@cached(ttl=120, cache=Cache.MEMORY)
async def get_admin_data(chat_id: int, bot: Bot) -> dict:
    """Busca e armazena em cache os IDs e usernames dos administradores."""
    try:
        logging.info(f"Cache miss. Buscando dados de administradores para o chat {chat_id}")
        admins = await bot.get_chat_administrators(chat_id)
        admin_data = {"ids": set(), "usernames": set()}
        for admin in admins:
            admin_data["ids"].add(admin.user.id)
            if admin.user.username:
                admin_data["usernames"].add(admin.user.username.lower())
        return admin_data
    except TelegramBadRequest as e:
        logging.error(f"Não foi possível buscar admins para o chat {chat_id}: {e}. O bot é admin?")
        return {"ids": set(), "usernames": set()}

async def is_user_admin(chat_id: int, user_id: int, bot: Bot) -> bool:
    """Verifica se um usuário é administrador usando o cache otimizado."""
    admin_data = await get_admin_data(chat_id, bot)
    return user_id in admin_data["ids"]

@dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text | F.contact | F.forward_origin)
async def moderate_group_messages(message: types.Message, bot: Bot):
    """Manipulador principal que orquestra a lógica de moderação."""
    if (not message.from_user or
        message.from_user.id == ANONYMOUS_ADMIN_ID or
        await is_user_admin(message.chat.id, message.from_user.id, bot)):
        return

    message_text = message.text or message.caption or ""

    if message_text and EMAIL_ONLY_REGEX.match(message_text):
        logging.info(f"Moderação abortada no chat {message.chat.id}: mensagem contém apenas um e-mail.")
        return
        
    if message_text.startswith('/'):
        return

    # --- IMPLEMENTAÇÃO: Estágio 0 - Verificação de Tolerância Zero ---
    # Este bloco tem prioridade máxima e contorna todas as outras lógicas.
    normalized_text = message_text.lower()
    # Usar \b para garantir que estamos verificando palavras inteiras e evitar falsos positivos (ex: "cpu").
    if normalized_text and any(re.search(r'\b' + re.escape(term) + r'\b', normalized_text) for term in INSTANT_BAN_TERMS):
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        logging.critical(f"VIOLAÇÃO GRAVE DETECTADA de '{message.from_user.full_name}' no chat {chat_id}. BANIMENTO IMEDIATO.")
        
        violation_type = "VIOLAÇÃO GRAVE (TOLERÂNCIA ZERO)"
        action_description = "<b>Consequência:</b> <b>BANIMENTO PERMANENTE E IMEDIATO</b> do grupo."
        header = "🚨 <b>VIOLAÇÃO DE TOLERÂNCIA ZERO</b> 🚨"
        motivo = "Conteúdo estritamente proibido detectado."
        
        warning_text = (
            f"{header}\n\n"
            f"A mensagem de {message.from_user.mention_html()} foi removida.\n"
            f"<b>Motivo:</b> <i>{motivo}</i>\n\n"
            f"{action_description}"
        )

        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            
            if LOG_CHANNEL_ID:
                await log_queue.put({
                    "user_id": user_id, "user_full_name": message.from_user.full_name,
                    "chat_id": chat_id, "chat_title": message.chat.title,
                    "action_description": action_description, "warn_count": "IMEDIATO",
                    "original_message": message_text if message_text else f"<{violation_type}>", "violation_type": violation_type
                })
            
            await message.reply(text=warning_text, parse_mode="HTML")
            await message.delete()
            
        except TelegramBadRequest as e:
            logging.error(f"Falha ao aplicar BANIMENTO IMEDIATO no grupo {chat_id}: {e}")
        except Exception as e:
            logging.error(f"Erro inesperado durante o BANIMENTO IMEDIATO: {e}")
        
        # Interrompe a execução aqui para garantir que nenhuma outra lógica seja processada.
        return

    # --- Pipeline de Verificação Padrão ---
    violation_type: Optional[str] = None
    
    if message_text and FORBIDDEN_CONTENT_REGEX.search(message_text):
        if "@admin" in message_text.lower():
            logging.info(f"Moderação abortada no chat {message.chat.id}: menção genérica '@admin' encontrada.")
            return

        mentioned_users = {
            message_text[entity.offset: entity.offset + entity.length].lstrip('@').lower()
            for entity in (message.entities or [])
            if entity.type == MessageEntityType.MENTION
        }
        
        if mentioned_users:
            admin_data = await get_admin_data(message.chat.id, bot)
            if not mentioned_users.isdisjoint(admin_data["usernames"]):
                logging.info(f"Moderação abortada no chat {message.chat.id}: menção a administrador específico encontrada.")
                return
        
        violation_type = "LINK/DIVULGAÇÃO"

    if not violation_type and (message.forward_origin or message.contact or (message_text and scta_analyzer.is_violation(message_text))):
        violation_type = "CONTEÚDO INAPROPRIADO"

    # --- Lógica de Punição Progressiva ---
    if violation_type:
        user_id = message.from_user.id
        chat_id = message.chat.id
        now = datetime.utcnow()
        
        logging.warning(f"Violação do tipo '{violation_type}' detectada de '{message.from_user.full_name}'. Procedendo...")
        
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute("SELECT warn_count, last_infraction_timestamp FROM infractions WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
            record = await cursor.fetchone()
            
            new_warn_count = 1
            if record:
                last_warn_count, last_timestamp = record
                cooldown_days = COOLDOWN_PERIODS_IN_DAYS.get(last_warn_count, 60)
                if now - datetime.fromtimestamp(last_timestamp) > timedelta(days=cooldown_days):
                    new_warn_count = 1
                else:
                    new_warn_count = last_warn_count + 1

            action_description = ""
            punishment_duration: Optional[timedelta] = None
            is_permanent_ban = False

            if new_warn_count == 1:
                punishment_duration = timedelta(days=1)
                action_description = f"<b>Consequência:</b> Silêncio de <b>1 DIA</b> 🗓️ (1º Aviso)"
            elif new_warn_count == 2:
                punishment_duration = timedelta(weeks=1)
                action_description = f"<b>Consequência:</b> Silêncio de <b>1 SEMANA</b> 📅 (2º Aviso)"
            elif new_warn_count == 3:
                punishment_duration = timedelta(days=30)
                action_description = f"<b>Consequência:</b> Silêncio de <b>1 MÊS</b> ❌ (3º Aviso)"
            else: # 4ª infração ou mais
                is_permanent_ban = True
                action_description = f"<b>Consequência:</b> <b>BANIMENTO PERMANENTE</b> do grupo ({new_warn_count}º Aviso)"

            if violation_type == "LINK/DIVULGAÇÃO":
                header = "🚫 <b>LINK/DIVULGAÇÃO PROIBIDO</b> 🚫"
                motivo = "Violação das regras de publicidade."
            else:
                header = "🚫 <b>MENSAGEM INAPROPRIADA</b> 🚫"
                motivo = "Violação das políticas de conteúdo do grupo."

            warning_text = (
                f"{header}\n\n"
                f"A mensagem de {message.from_user.mention_html()} foi removida.\n"
                f"<b>Motivo:</b> <i>{motivo}</i>\n\n"
                f"{action_description}"
            )

            await db.execute(
                "INSERT OR REPLACE INTO infractions (user_id, chat_id, warn_count, last_infraction_timestamp) VALUES (?, ?, ?, ?)",
                (user_id, chat_id, new_warn_count, int(now.timestamp()))
            )
            await db.commit()

            try:
                if is_permanent_ban:
                    await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                elif punishment_duration:
                    await bot.restrict_chat_member(
                        chat_id=chat_id, user_id=user_id,
                        permissions=types.ChatPermissions(can_send_messages=False),
                        until_date=now + punishment_duration
                    )

                logging.info(f"Ação de moderação Nível {new_warn_count} concluída para '{message.from_user.full_name}'.")
                if LOG_CHANNEL_ID:
                    await log_queue.put({
                        "user_id": user_id, "user_full_name": message.from_user.full_name,
                        "chat_id": chat_id, "chat_title": message.chat.title,
                        "action_description": action_description, "warn_count": new_warn_count,
                        "original_message": message_text if message_text else f"<{violation_type}>", "violation_type": violation_type
                    })
                
                await message.reply(text=warning_text, parse_mode="HTML")
                await message.delete()

            except TelegramBadRequest as e:
                logging.error(f"Falha ao aplicar uma ação de interface no grupo {chat_id} (punição e log já efetuados): {e}")
            except Exception as e:
                logging.error(f"Erro inesperado durante a aplicação da punição: {e}")

# --- Ponto de Entrada da Aplicação ---
async def main():
    """Inicializa o banco de dados, o bot e as tarefas de fundo."""
    await setup_database()
    
    bot = Bot(token=BOT_TOKEN)
    
    if LOG_CHANNEL_ID:
        asyncio.create_task(log_processor_task(bot))
        logging.info("Tarefa de processamento de logs iniciada.")

    logging.info("Iniciando o bot Vigia em modo de polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot desligado pelo usuário.")