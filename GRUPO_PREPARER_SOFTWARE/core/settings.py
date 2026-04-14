import os
from pydantic_settings import BaseSettings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE_PATH = os.path.join(BASE_DIR, '.env')

class Settings(BaseSettings):
    """
    Roteador imutável de variáveis de ambiente.
    Isola o fluxo de execução das possíveis falhas de leitura do S.O.
    """
    API_ID: int
    API_HASH: str
    PHONE: str
    BOT_TOKEN: str
    
    # Ingestão de Modificadores:
    BOT_USERNAME: str
    AVATAR_PATH: str

    class Config:
        env_file = ENV_FILE_PATH
        env_file_encoding = "utf-8"

# Instância termicamente imutável do objeto
config = Settings()

# --- Drenagem de Infraestrutura Física ---
# Garante a existência do estado persistente (I/O) antes de disparar EventLoops
SESSION_DIR = os.path.join(BASE_DIR, 'sessions')
DATA_DIR = os.path.join(BASE_DIR, 'data')

os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
