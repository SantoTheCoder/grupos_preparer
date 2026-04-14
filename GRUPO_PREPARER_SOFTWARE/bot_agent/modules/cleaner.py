import logging
from telethon import events
from telethon.tl.types import MessageActionChatAddUser, MessageActionChatDeleteUser, MessageActionChatJoinedByLink, MessageActionPinMessage
from core.settings import config

logger = logging.getLogger("ZELADOR.Limpador")

def get_cleaner_handler():
    """
    Fábrica do Handler para Aniquilação de Sujeira Visual.
    Acorda passivamente sempre que o Telegram notifica um ChatAction.
    """
    
    @events.register(events.ChatAction)
    async def cleaner_handler(event):
        if not config.ENABLE_SERVICE_CLEANER:
            return
            
        try:
            # Pega o objeto da ação pura
            action = getattr(event.message, 'action', None)
            if action:
                # O Telegram emite ações nativas. Nós pegamos as principais que sujam a tela.
                # Se desejar pode expandir para apagar tudo isinstance(action, (MessageAction...))
                logger.info(f"🧹 Detectei sujeira em [{event.chat_id}]. Apagando Serviço: {type(action).__name__}")
                await event.delete()
        except Exception as e:
            logger.warning(f"⚠️ Falha ao limpar mensagem de serviço em {event.chat_id}: {e}")

    return cleaner_handler
