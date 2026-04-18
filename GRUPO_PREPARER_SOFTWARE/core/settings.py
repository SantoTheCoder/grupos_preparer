import os

from pydantic_settings import BaseSettings


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")


def _resolve_path(path_value: str) -> str:
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(BASE_DIR, path_value)


class Settings(BaseSettings):
    API_ID: int
    API_HASH: str
    PHONE: str
    BOT_TOKEN: str

    BOT_USERNAME: str = "@FiscalDoGrupoBot"
    FISCAL_BOT_USERNAME: str = "@FiscalDoGrupoBot"
    GIFT_BOT_USERNAME: str = "@IaDetetive_Bot"

    AVATAR_PATH: str = "foto_grupo.png"
    BANNER_FIXADO_PATH: str = "banner_fixado.png"
    DIRETORIO_TEXTO_FIXADO: str = "data/pinned_message.txt"
    DIRETORIO_DESCRICAO_GRUPO: str = "data/group_description.txt"

    DRONE_ACCOUNTS_PATH: str = "data/accounts_mapping.json"
    GROUP_QUEUE_PATH: str = "data/group_seed_queue.json"
    GROUP_DATABASE_PATH: str = "data/database_grupos.json"
    GIFT_INJECTION_STATE_PATH: str = "data/gift_injection_state.json"

    GIFT_VALUE: int = 500
    ENABLE_SERVICE_CLEANER: bool = True

    class Config:
        env_file = ENV_FILE_PATH
        env_file_encoding = "utf-8"

    @property
    def avatar_file(self) -> str:
        return _resolve_path(self.AVATAR_PATH)

    @property
    def banner_file(self) -> str:
        return _resolve_path(self.BANNER_FIXADO_PATH)

    @property
    def pinned_message_file(self) -> str:
        return _resolve_path(self.DIRETORIO_TEXTO_FIXADO)

    @property
    def group_description_file(self) -> str:
        return _resolve_path(self.DIRETORIO_DESCRICAO_GRUPO)

    @property
    def accounts_file(self) -> str:
        return _resolve_path(self.DRONE_ACCOUNTS_PATH)

    @property
    def group_queue_file(self) -> str:
        return _resolve_path(self.GROUP_QUEUE_PATH)

    @property
    def group_database_file(self) -> str:
        return _resolve_path(self.GROUP_DATABASE_PATH)

    @property
    def gift_injection_state_file(self) -> str:
        return _resolve_path(self.GIFT_INJECTION_STATE_PATH)


config = Settings()

SESSION_DIR = os.path.join(BASE_DIR, "sessions")
DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
