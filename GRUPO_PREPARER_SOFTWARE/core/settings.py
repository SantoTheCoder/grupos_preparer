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
    SUB_MASTER_NAME: str = "Sub Master"
    SUB_MASTER_PHONE: str = ""
    SUB_MASTER_API_ID: int = 0
    SUB_MASTER_API_HASH: str = ""
    BOT_TOKEN: str
    MASTER_SESSION_NAME: str = "user_account"
    SUB_MASTER_SESSION_NAME: str = "sub_master"

    BOT_USERNAME: str = "@FiscalDoGrupoBot"
    FISCAL_BOT_USERNAME: str = "@FiscalDoGrupoBot"
    GIFT_BOT_USERNAME: str = "@IaDetetive_Bot"

    AVATAR_PATH: str = "foto_grupo.png"
    BANNER_FIXADO_PATH: str = "banner_fixado.png"
    DIRETORIO_TEXTO_FIXADO: str = "data/pinned_message.txt"
    DIRETORIO_DESCRICAO_GRUPO: str = "data/group_description.txt"

    ACCOUNTS_PATH: str = "data/accounts.json"
    GROUPS_PATH: str = "data/groups.json"

    GIFT_VALUE: int = 500
    ENABLE_SERVICE_CLEANER: bool = True
    ACTION_DELAY_SECONDS: float = 2.5
    ACTION_DELAY_JITTER_SECONDS: float = 1.5
    GIFT_RESPONSE_WAIT_SECONDS: float = 4.0
    GROUP_COOLDOWN_SECONDS: float = 10.0

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
        return _resolve_path(self.ACCOUNTS_PATH)

    @property
    def groups_file(self) -> str:
        return _resolve_path(self.GROUPS_PATH)

    @property
    def master_session_file(self) -> str:
        return os.path.join(SESSION_DIR, f"{self.MASTER_SESSION_NAME}.session")

    @property
    def sub_master_session_file(self) -> str:
        return os.path.join(SESSION_DIR, f"{self.SUB_MASTER_SESSION_NAME}.session")


SESSION_DIR = os.path.join(BASE_DIR, "sessions")
DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

config = Settings()
