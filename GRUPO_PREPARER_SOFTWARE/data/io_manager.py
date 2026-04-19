import json
import logging
import os
from typing import Any

from core.settings import config


logger = logging.getLogger(__name__)


class PersistenceManager:
    def __init__(self):
        self.accounts_path = config.accounts_file
        self.groups_path = config.groups_file

    def _read_json(self, path: str, default: Any):
        if not os.path.exists(path):
            return default

        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                return json.load(file_obj)
        except (OSError, json.JSONDecodeError):
            logger.warning("Falha ao ler %s. Usando valor padrao.", path)
            return default

    def _write_json(self, path: str, data: Any):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(data, file_obj, indent=4, ensure_ascii=False)

    def load_accounts(self) -> list[dict]:
        return self._read_json(self.accounts_path, [])

    def save_accounts(self, accounts: list[dict]):
        self._write_json(self.accounts_path, accounts)

    def load_groups(self) -> list[dict]:
        return self._read_json(self.groups_path, [])

    def save_groups(self, groups: list[dict]):
        self._write_json(self.groups_path, groups)

    def upsert_group_record(self, record: dict):
        groups = self.load_groups()
        group_id = record.get("group_id")
        internal_code = record.get("internal_code")
        account_id = record.get("account_id")

        for index, existing in enumerate(groups):
            if group_id and existing.get("group_id") == group_id:
                groups[index] = {**existing, **record}
                self.save_groups(groups)
                return

            if (
                internal_code
                and account_id
                and existing.get("internal_code") == internal_code
                and existing.get("account_id") == account_id
            ):
                groups[index] = {**existing, **record}
                self.save_groups(groups)
                return

        groups.append(record)
        self.save_groups(groups)

    # Wrappers de compatibilidade para scripts antigos ainda presentes no repo.
    def save_state(self, groups: list[dict]):
        self.save_groups(groups)

    def load_state(self) -> list[dict]:
        return self.load_groups()

    def load_seed_queue(self) -> list[dict]:
        return self.load_groups()

    def save_seed_queue(self, groups: list[dict]):
        self.save_groups(groups)

    def load_group_database(self) -> list[dict]:
        return self.load_groups()

    def save_group_database(self, groups: list[dict]):
        self.save_groups(groups)
