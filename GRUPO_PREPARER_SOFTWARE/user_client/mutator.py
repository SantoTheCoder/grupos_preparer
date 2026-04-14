import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
import asyncio
from telethon import TelegramClient
from telethon.tl.types import Chat, Channel, InputChatUploadedPhoto, ChatAdminRights
from telethon.tl.functions.channels import EditAdminRequest, EditTitleRequest, EditPhotoRequest as ChannelEditPhotoRequest
from telethon.tl.functions.messages import EditChatAboutRequest, EditChatTitleRequest, EditChatPhotoRequest
from telethon.errors.rpcerrorlist import ChatNotModifiedError, FloodWaitError
from core.settings import config, SESSION_DIR, BASE_DIR, DATA_DIR
from data.io_manager import PersistenceManager
import argparse
import sys
import random

# Força o terminal do Windows a suportar renderização estrita de UTF-8 (Destrói UnicodeEncodeError)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Monkey-Patching Brutal no MTProto
# Obliterando a validação de Tempo da API do Telegram (Isso força o bypass do erro: "Server sent a very new message")
import telethon.network.mtprotostate
telethon.network.mtprotostate.MSG_TOO_OLD_DELTA = 999999999
telethon.network.mtprotostate.MSG_TOO_NEW_DELTA = 999999999

# Motor de Observabilidade Absoluta (Tracing Assíncrono)
log_file = os.path.join(BASE_DIR, 'debug_mutator.log')
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
# Isolamento do ruído excessivo de pacotes TCP do Telethon
logging.getLogger('telethon').setLevel(logging.INFO)
logger = logging.getLogger("MUTADOR_MESTRE")

class GroupMutator:
    """Implementa o isolamento transacional sobre metadados dos grupos."""
    def __init__(self):
        session_file = os.path.join(SESSION_DIR, 'user_account.session')
        # Injeção para evitar detecção de Scraper e Drops de Conexão no DataCenter:
        self.client = TelegramClient(
            session_file, 
            config.API_ID, 
            config.API_HASH,
            device_model="Desktop Windows",
            system_version="Windows 11",
            app_version="4.10.3",
            lang_code="pt-br",
            system_lang_code="pt-br"
        )
        self.persistence = PersistenceManager()

    async def run_mutations(self, test_mode: bool = False):
        await self.client.start(phone=config.PHONE)
        logger.info("🔌 [MUTADOR FRONTAL] Conexão consolidada.")

        groups = self.persistence.load_state()
        if not groups:
            logger.error("🛑 PARADA CRÍTICA: Base de dados groups_data.json extinta ou vazia.")
            return

        if test_mode:
            logger.warning("🧪 MODO DE TESTE ATIVADO: Apenas o PRIMEIRO grupo válido será homologado.")

        # Upload prévio da imagem para reciclar ponteiro de Bytes HTTP.
        # Assim poupamos rede: subimos uma foto pro Telegram e usamos a ID dela.
        uploaded_photo = None
        if os.path.exists(config.AVATAR_PATH):
            logger.info("🔵 Foto alocada na memória...")
            try:
                uploaded_photo = await self.client.upload_file(config.AVATAR_PATH)
            except Exception as e:
                logger.error(f"Erro no envio binário da foto: {e}")
        else:
            logger.warning("🟡 Caminho da foto em AVATAR_PATH inexistente. Ignorando imagem.")

        try:
            bot_entity = await self.client.get_entity(config.BOT_USERNAME)
        except ValueError:
            logger.error(f"🛑 CRÍTICO: Não enxerguei o bot '{config.BOT_USERNAME}'. Ele não existe ou você não tem acesso.")
            return

        rights = ChatAdminRights(
            change_info=True, post_messages=True, edit_messages=True,
            delete_messages=True, ban_users=True, invite_users=True,
            pin_messages=True, add_admins=False, anonymous=False, manage_call=True
        )

        for group in groups:
            entity_id = group["id"]
            new_name = group.get("new_name", "").strip()
            
            if group.get("status") == "MUTADO":
                logger.info(f"⏭️ Pulando ID [{entity_id}] - Já consta como MUTADO no snapshot.")
                continue

            if not new_name:
                logger.warning(f"⏩ Pulando ID [{entity_id}] - string 'new_name' estéril no JSON.")
                continue

            try:
                entity = await self.client.get_entity(entity_id)
                logger.info(f"⚡ Disparando rotina para Chat Absoluto O(1): [{new_name}]")
                
                # 1. Zeroing - Deletar Histórico da Matriz
                logger.info("   -> [1/4] Aniquilando resíduos anteriores...")
                async for msg in self.client.iter_messages(entity_id, limit=30):
                    await msg.delete()

                # 2. Mutação Descritiva
                logger.info("   -> [2/4] Sobrescrevendo Título, Descrição e Foto...")
                
                with open(os.path.join(DATA_DIR, 'group_description.txt'), 'r', encoding='utf-8') as f:
                    new_about = f.read()

                if isinstance(entity, Channel): # Serve também para SuperGroups
                    try: await self.client(EditTitleRequest(channel=entity, title=new_name))
                    except Exception as e: 
                        if "modified" not in str(e).lower() and "changed" not in str(e).lower(): logger.warning(f"Erro ao alterar título: {e}")
                    
                    try: await self.client(EditChatAboutRequest(peer=entity, about=new_about))
                    except Exception as e:
                        if "modified" not in str(e).lower() and "changed" not in str(e).lower(): logger.warning(f"Erro ao alterar about: {e}")
                    
                    if uploaded_photo:
                        try: await self.client(ChannelEditPhotoRequest(channel=entity, photo=uploaded_photo))
                        except Exception as e:
                            if "modified" not in str(e).lower() and "changed" not in str(e).lower(): logger.warning(f"Erro ao alterar foto: {e}")
                    
                    logger.info("   -> [3/4] Promovendo Microsserviço BOT à Orquestrador...")
                    try:
                        await self.client(EditAdminRequest(channel=entity, user_id=bot_entity, admin_rights=rights, rank="Bot Oficial"))
                    except Exception as e:
                        logger.warning(f"   -> [3/4 AVISO] Telegram bloqueou promoção: {e}. Adicione o bot manualmente.")
                else:
                    try: await self.client(EditChatTitleRequest(chat_id=entity_id, title=new_name))
                    except Exception as e:
                        if "modified" not in str(e).lower() and "changed" not in str(e).lower(): logger.warning(f"Erro ao alterar título: {e}")
                    
                    try: await self.client(EditChatAboutRequest(peer=entity_id, about=new_about))
                    except Exception as e:
                        if "modified" not in str(e).lower() and "changed" not in str(e).lower(): logger.warning(f"Erro ao alterar about: {e}")
                    
                    if uploaded_photo:
                        try: await self.client(EditChatPhotoRequest(chat_id=entity_id, photo=uploaded_photo))
                        except Exception as e:
                            if "modified" not in str(e).lower() and "changed" not in str(e).lower(): logger.warning(f"Erro ao alterar foto: {e}")
                    logger.warning("   -> [3/4 ATENÇÃO] Grupos normais não podem ter Bot promovido como super admin. Bot ignorado neste aqui.")

                # 3. Postar e Fixar Imutável
                logger.info("   -> [4/4] Cravação permanente da mensagem do topo...")
                
                # Leitura térmica do disco devido a quebras de linha maciças
                with open(os.path.join(DATA_DIR, 'pinned_message.txt'), 'r', encoding='utf-8') as f:
                    pin_text = f.read()

                banner_path = os.path.join(BASE_DIR, 'banner_fixado.png')
                msg_to_pin = None
                
                if os.path.exists(banner_path):
                    if len(pin_text) > 1000:
                        logger.warning("   -> [4/4 AVISO] O seu texto ultrapassa os 1024 caracteres. Enviando Imagem e depois Texto.")
                        msg_to_pin = await self.client.send_file(entity_id, banner_path)
                        await self.client.send_message(entity_id, pin_text, parse_mode='html')
                    else:
                        msg_to_pin = await self.client.send_file(
                            entity_id, 
                            banner_path, 
                            caption=pin_text,
                            parse_mode='html' # Garante leitura de formatações futuras se usarmos
                        )
                else:
                    msg_to_pin = await self.client.send_message(entity_id, pin_text, parse_mode='html')
                    
                try:
                    await self.client.pin_message(entity_id, msg_to_pin.id, notify=True)
                except FloodWaitError as e:
                    logger.warning(f"   -> [4/4 AVISO] Telegram impôs limite Anti-Spam de {e.seconds}s apenas para fixação neste grupo. Prosseguindo...")
                except Exception as e:
                    if "not modified" not in str(e).lower() and "not changed" not in str(e).lower():
                        logger.warning(f"   -> [4/4 AVISO] Não foi possível fixar: {e}")

                # Persistência Ativa de Checkpoint - Salva no arquivo imediatamente após o grupo
                group['status'] = 'MUTADO'
                self.persistence.save_state(groups)
                
                # Exportação Limpa para a Orquestração do Bot de Produção (Fase 4)
                self.persistence.save_production_group(entity_id, new_name, group.get("link", ""))

                logger.info(f"✅ CONCLUÍDO: [{new_name}] blindado com sucesso e status salvo no disco.")
            
            except Exception as e:
                logger.error(f"❌ ATENÇÃO: Falha arquitetural em [{new_name}]: {e}")

            # Despressurizador térmico: Jitter de 18 a 32s protege contra Block rate-limit 429 nas varreduras.
            await asyncio.sleep(random.uniform(18, 32))

            if test_mode:
                logger.warning("🧪 MODO DE TESTE CONCLUÍDO: Abortando restante da matriz.")
                break

        logger.info("🧊 Pipeline de Mutação Encerrado.")
        await self.client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mutador de MetaDados Telethon.")
    parser.add_argument("--test", action="store_true", help="Executa a mutação apenas no primeiro grupo para testar o Anti-Spam.")
    args = parser.parse_args()

    mutator = GroupMutator()
    asyncio.run(mutator.run_mutations(test_mode=args.test))
