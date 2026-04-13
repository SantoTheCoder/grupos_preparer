import json
import csv
import os
import logging
from core.settings import DATA_DIR

logger = logging.getLogger(__name__)

class PersistenceManager:
    """I/O Frio. Salva o estado transacional dos canais mapeados minimizando batidas de disco."""
    def __init__(self):
        self.json_path = os.path.join(DATA_DIR, 'groups_data.json')
        self.csv_path = os.path.join(DATA_DIR, 'mapping.csv')

    def save_state(self, groups: list[dict]):
        """
        Consolida a matriz de dados [ID x Link x Nome Antigo x Novo Nome]
        Groups é uma listagem em memória injetada diretamente via dump atômico.
        """
        # Commit JSON primário para leitura do Bot
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(groups, f, indent=4, ensure_ascii=False)
        
        # Branch CSV para debug/humano (isolamento documental)
        if groups:
            keys = groups[0].keys()
            with open(self.csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(groups)
        
        logger.info(f"💾 Memória térmica convertida em I/O: {len(groups)} alvos persistidos.")

    def load_state(self) -> list[dict]:
        """Recupera o mapeamento salvo para orquestradores secundários (Bots/Mutators)."""
        if os.path.exists(self.json_path):
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

