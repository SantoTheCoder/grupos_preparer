import json
import logging
import os
import re
from typing import Any

from core.settings import config


logger = logging.getLogger(__name__)

CANONICAL_GROUP_FIELDS = (
    "id",
    "link",
    "name",
    "owner",
    "phone",
    "api_id",
    "api_hash",
)
LEGACY_ALIAS_MAP = {
    "group_id": "id",
    "invite_link": "link",
    "group_link": "link",
    "group_name": "name",
}
ASCII_ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
STYLED_ALNUM = "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
UNICODE_MAP = str.maketrans(
    ASCII_ALNUM,
    STYLED_ALNUM,
)
REVERSE_UNICODE_MAP = str.maketrans(STYLED_ALNUM, ASCII_ALNUM)
BASE_NODE_NUMBER = 31


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    return f"+{digits}"


def first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def build_account_id(name: str, phone: str) -> str:
    base_name = re.sub(r"[^a-z0-9]+", "-", (name or "drone").strip().lower()).strip("-")
    digits = re.sub(r"\D", "", phone or "")
    suffix = digits[-4:] if digits else "0000"
    return f"{base_name}-{suffix}"


def extract_internal_code(name: str) -> str | None:
    normalized_name = (name or "").translate(REVERSE_UNICODE_MAP)
    match = re.search(r"#([A-Z]\d{2})", normalized_name)
    if not match:
        return None
    return match.group(1)


def build_operational_code(index: int, group_name: str | None = None) -> tuple[str, str, str]:
    internal_code = extract_internal_code(group_name or "")
    if internal_code is None:
        bot_number = BASE_NODE_NUMBER + index
        letter_index = (bot_number - 1) // 10
        unit_value = ((bot_number - 1) % 10) + 1
        letter = chr(ord("A") + letter_index)
        internal_code = f"{letter}{unit_value:02d}"

    letter = internal_code[0]
    unit_value = int(internal_code[1:])
    bot_number = (ord(letter) - ord("A")) * 10 + unit_value
    styled_code = internal_code.translate(UNICODE_MAP)
    node_operacional = f"bot_{bot_number:03d}_novo"
    return internal_code, styled_code, node_operacional


def build_group_name(index: int, internal_code: str | None = None) -> str:
    _, styled_code, _ = build_operational_code(index, f"#{internal_code}" if internal_code else None)
    return f"🕵️‍♂️ 𝗩Λ𝗥𝗥𝗘𝗗𝗨𝗥Λ 𝗚𝗥Λ́𝗧𝗜𝗦 ［#{styled_code}］ ⚡️ 〘 𝗜Λ 𝗗𝗘𝗧𝗘𝗧𝗜𝗩𝗘 〙"


class PersistenceManager:
    def __init__(self):
        self.accounts_path = config.accounts_file
        self.inventory_path = config.group_inventory_file
        self.runtime_path = config.group_runtime_file
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

    def _normalize_inventory_entry(self, entry: dict, index: int, accounts_by_phone: dict[str, dict]) -> dict:
        phone = normalize_phone(entry.get("phone", ""))
        account = accounts_by_phone.get(phone, {})
        normalized = {
            "id": first_not_none(entry.get("id"), entry.get("group_id")),
            "link": entry.get("link") or entry.get("invite_link") or entry.get("group_link"),
            "name": entry.get("name") or build_group_name(index),
            "owner": entry.get("owner") or account.get("name", ""),
            "phone": phone,
            "api_id": entry.get("api_id") or account.get("api_id") or 0,
            "api_hash": entry.get("api_hash") or account.get("api_hash") or "",
        }
        return normalized

    def _normalize_runtime_entry(self, entry: dict, inventory_entry: dict, index: int) -> dict:
        internal_code, _, node_operacional = build_operational_code(index, inventory_entry.get("name"))
        runtime = {
            key: value
            for key, value in entry.items()
            if key not in CANONICAL_GROUP_FIELDS and key not in LEGACY_ALIAS_MAP
        }
        runtime["phone"] = inventory_entry.get("phone", "")
        runtime["owner"] = inventory_entry.get("owner", "")
        runtime["account_id"] = runtime.get("account_id") or build_account_id(
            inventory_entry.get("owner", ""),
            inventory_entry.get("phone", ""),
        )
        runtime["internal_code"] = internal_code
        runtime["node_operacional"] = node_operacional
        return runtime

    def _merge_group_record(self, inventory_entry: dict, runtime_entry: dict) -> dict:
        merged = {**inventory_entry, **runtime_entry}
        merged["group_id"] = merged.get("id")
        merged["invite_link"] = merged.get("link")
        merged["group_link"] = merged.get("link")
        merged["group_name"] = merged.get("name")
        merged["account_id"] = merged.get("account_id") or build_account_id(
            merged.get("owner", ""),
            merged.get("phone", ""),
        )
        return merged

    def _sync_accounts_from_inventory(self, inventory: list[dict]):
        if not inventory:
            return

        existing_accounts = self._read_json(self.accounts_path, [])
        existing_by_phone = {
            normalize_phone(account.get("phone", "")): account
            for account in existing_accounts
            if isinstance(account, dict) and normalize_phone(account.get("phone", ""))
        }
        synced_accounts = []
        seen_phones: set[str] = set()

        for item in inventory:
            phone = normalize_phone(item.get("phone", ""))
            if not phone or phone in seen_phones:
                continue

            seen_phones.add(phone)
            existing = existing_by_phone.get(phone, {})
            synced_accounts.append(
                {
                    **existing,
                    "account_id": build_account_id(item.get("owner", ""), phone),
                    "name": item.get("owner", ""),
                    "phone": phone,
                    "api_id": item.get("api_id") or existing.get("api_id") or 0,
                    "api_hash": item.get("api_hash") or existing.get("api_hash") or "",
                }
            )

        self._write_json(self.accounts_path, synced_accounts)

    def _write_compat_groups(self, inventory: list[dict], runtime: list[dict]):
        # groups.json foi mantido apenas como espelho de compatibilidade.
        # O fluxo novo usa somente group_inventory.json + group_runtime.json.
        return None

    def _migrate_legacy_groups_if_needed(self):
        inventory_exists = os.path.exists(self.inventory_path)
        runtime_exists = os.path.exists(self.runtime_path)
        if inventory_exists and runtime_exists:
            return

        legacy_groups = self._read_json(self.groups_path, [])
        if not legacy_groups:
            if not inventory_exists:
                self._write_json(self.inventory_path, [])
            if not runtime_exists:
                self._write_json(self.runtime_path, [])
            if os.path.exists(self.groups_path):
                try:
                    os.remove(self.groups_path)
                except OSError:
                    logger.warning("Falha ao remover groups.json legado.")
            return

        logger.info("Migrando data/groups.json para inventario e runtime separados.")
        accounts = self._read_json(self.accounts_path, [])
        accounts_by_phone = {
            normalize_phone(account.get("phone", "")): account
            for account in accounts
            if isinstance(account, dict) and normalize_phone(account.get("phone", ""))
        }

        inventory: list[dict] = []
        runtime: list[dict] = []
        for index, legacy_entry in enumerate(legacy_groups):
            phone = normalize_phone(legacy_entry.get("phone", ""))
            account = accounts_by_phone.get(phone, {})
            source_entry = {**account, **legacy_entry}
            inventory_entry = self._normalize_inventory_entry(source_entry, index, accounts_by_phone)
            runtime_entry = self._normalize_runtime_entry(source_entry, inventory_entry, index)
            inventory.append(inventory_entry)
            runtime.append(runtime_entry)

        self._write_json(self.inventory_path, inventory)
        self._write_json(self.runtime_path, runtime)
        self._sync_accounts_from_inventory(inventory)
        if os.path.exists(self.groups_path):
            try:
                os.remove(self.groups_path)
            except OSError:
                logger.warning("Falha ao remover groups.json legado.")

    def _load_inventory_runtime(self) -> tuple[list[dict], list[dict]]:
        self._migrate_legacy_groups_if_needed()

        raw_inventory = self._read_json(self.inventory_path, [])
        raw_runtime = self._read_json(self.runtime_path, [])
        accounts = self._read_json(self.accounts_path, [])
        accounts_by_phone = {
            normalize_phone(account.get("phone", "")): account
            for account in accounts
            if isinstance(account, dict) and normalize_phone(account.get("phone", ""))
        }
        inventory: list[dict] = []
        runtime: list[dict] = []
        for index, item in enumerate(raw_inventory):
            inventory_entry = self._normalize_inventory_entry(item, index, accounts_by_phone)
            raw_runtime_entry = raw_runtime[index] if index < len(raw_runtime) and isinstance(raw_runtime[index], dict) else {}
            runtime_entry = self._normalize_runtime_entry(raw_runtime_entry, inventory_entry, index)
            inventory.append(inventory_entry)
            runtime.append(runtime_entry)

        self._write_json(self.inventory_path, inventory)
        self._write_json(self.runtime_path, runtime)
        self._sync_accounts_from_inventory(inventory)
        return inventory, runtime

    def load_accounts(self) -> list[dict]:
        self._migrate_legacy_groups_if_needed()
        inventory = self._read_json(self.inventory_path, [])
        if inventory:
            self._sync_accounts_from_inventory(inventory)
        return self._read_json(self.accounts_path, [])

    def save_accounts(self, accounts: list[dict]):
        self._write_json(self.accounts_path, accounts)

    def load_inventory(self) -> list[dict]:
        inventory, _ = self._load_inventory_runtime()
        return inventory

    def save_inventory(self, inventory: list[dict]):
        accounts = self._read_json(self.accounts_path, [])
        accounts_by_phone = {
            normalize_phone(account.get("phone", "")): account
            for account in accounts
            if isinstance(account, dict) and normalize_phone(account.get("phone", ""))
        }
        _, existing_runtime = self._load_inventory_runtime()

        normalized_inventory: list[dict] = []
        normalized_runtime: list[dict] = []
        for index, item in enumerate(inventory):
            inventory_entry = self._normalize_inventory_entry(item, index, accounts_by_phone)
            existing_runtime_entry = existing_runtime[index] if index < len(existing_runtime) and isinstance(existing_runtime[index], dict) else {}
            runtime_entry = self._normalize_runtime_entry(existing_runtime_entry, inventory_entry, index)
            normalized_inventory.append(inventory_entry)
            normalized_runtime.append(runtime_entry)

        self._write_json(self.inventory_path, normalized_inventory)
        self._write_json(self.runtime_path, normalized_runtime)
        self._sync_accounts_from_inventory(normalized_inventory)

    def load_runtime(self) -> list[dict]:
        _, runtime = self._load_inventory_runtime()
        return runtime

    def save_runtime(self, runtime: list[dict]):
        inventory, _ = self._load_inventory_runtime()
        normalized_runtime: list[dict] = []

        for index, item in enumerate(inventory):
            raw_runtime_entry = runtime[index] if index < len(runtime) and isinstance(runtime[index], dict) else {}
            runtime_entry = self._normalize_runtime_entry(raw_runtime_entry, item, index)
            normalized_runtime.append(runtime_entry)

        self._write_json(self.runtime_path, normalized_runtime)

    def load_groups(self) -> list[dict]:
        inventory, runtime = self._load_inventory_runtime()
        return [self._merge_group_record(inv, run) for inv, run in zip(inventory, runtime)]

    def save_groups(self, groups: list[dict]):
        accounts = self._read_json(self.accounts_path, [])
        accounts_by_phone = {
            normalize_phone(account.get("phone", "")): account
            for account in accounts
            if isinstance(account, dict) and normalize_phone(account.get("phone", ""))
        }
        inventory: list[dict] = []
        runtime: list[dict] = []

        for index, record in enumerate(groups):
            inventory_entry = self._normalize_inventory_entry(record, index, accounts_by_phone)
            runtime_entry = self._normalize_runtime_entry(record, inventory_entry, index)
            inventory.append(inventory_entry)
            runtime.append(runtime_entry)

        self._write_json(self.inventory_path, inventory)
        self._write_json(self.runtime_path, runtime)
        self._sync_accounts_from_inventory(inventory)

    def upsert_group_record(self, record: dict):
        groups = self.load_groups()
        target_id = record.get("id", record.get("group_id"))
        target_phone = record.get("phone")
        target_account_id = record.get("account_id")
        target_internal_code = record.get("internal_code")

        for index, existing in enumerate(groups):
            if target_id is not None and existing.get("id") == target_id:
                groups[index] = {**existing, **record}
                self.save_groups(groups)
                return

            if target_phone and normalize_phone(existing.get("phone", "")) == normalize_phone(target_phone):
                groups[index] = {**existing, **record}
                self.save_groups(groups)
                return

            if (
                target_account_id
                and target_internal_code
                and existing.get("account_id") == target_account_id
                and existing.get("internal_code") == target_internal_code
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
