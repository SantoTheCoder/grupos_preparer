import json
import logging
import os
from typing import Any

from core.settings import config


logger = logging.getLogger(__name__)


class PersistenceManager:
    def __init__(self):
        self.accounts_path = config.accounts_file
        self.queue_path = config.group_queue_file
        self.database_path = config.group_database_file
        self.gift_state_path = config.gift_injection_state_file

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

    def load_seed_queue(self) -> list[dict]:
        return self._read_json(self.queue_path, [])

    def save_seed_queue(self, groups: list[dict]):
        self._write_json(self.queue_path, groups)

    def load_group_database(self) -> list[dict]:
        return self._read_json(self.database_path, [])

    def save_group_database(self, groups: list[dict]):
        self._write_json(self.database_path, groups)

    def upsert_group_record(self, record: dict):
        groups = self.load_group_database()
        group_id = record.get("group_id")
        internal_code = record.get("internal_code")
        owner = record.get("owner")

        for index, existing in enumerate(groups):
            if group_id and existing.get("group_id") == group_id:
                groups[index] = {**existing, **record}
                self.save_group_database(groups)
                return

            if (
                internal_code
                and owner
                and existing.get("internal_code") == internal_code
                and existing.get("owner") == owner
            ):
                groups[index] = {**existing, **record}
                self.save_group_database(groups)
                return

        groups.append(record)
        self.save_group_database(groups)

    def save_gift_state(self, state: dict):
        self._write_json(self.gift_state_path, state)

    def load_gift_state(self) -> dict:
        return self._read_json(
            self.gift_state_path,
            {"version": 1, "groups": {}, "generated_codes": {}},
        )

    # Wrappers de compatibilidade para scripts antigos ainda presentes no repo.
    def save_state(self, groups: list[dict]):
        self.save_group_database(groups)

    def load_state(self) -> list[dict]:
        return self.load_group_database()
