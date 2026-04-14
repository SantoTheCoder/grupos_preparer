import os
import json
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.settings import DATA_DIR
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def to_math_bold(text: str) -> str:
    """Modificador de strings para Unicode Bold (Mathematical Sans-Serif)."""
    mapping = {
        'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙', 'G': '𝗚', 
        'H': '𝗛', 'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟', 'M': '𝗠', 'N': '𝗡', 
        'O': '𝗢', 'P': '𝗣', 'Q': '𝗤', 'R': '𝗥', 'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 
        'V': '𝗩', 'W': '𝗪', 'X': '𝗫', 'Y': '𝗬', 'Z': '𝗭',
        '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', 
        '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵'
    }
    return "".join(mapping.get(c, c) for c in text.upper())

def apply_names():
    """Injeta a métrica de nomenclatura exata de forma O(N)."""
    json_path = os.path.join(DATA_DIR, 'groups_data.json')
    if not os.path.exists(json_path):
        logger.error("Fluxo interrompido: 'groups_data.json' inexistente. Dispare o extractor.py primeiro!")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        groups = json.load(f)

    if not groups:
        logger.error("JSON sem nós. Extração primária corrompida ou abortada.")
        return

    for i, group in enumerate(groups, start=1):
        # Mapeamento do Padrão Decimal de Letras (1-10 -> A, 11-20 -> B)
        # Ex: i=1 -> idx=0 (A), number=1. i=11 -> idx=1 (B), number=1.
        letter_idx = (i - 1) // 10
        number = ((i - 1) % 10) + 1
        
        # Evita 'overflow' se passarem de 260 grupos
        if letter_idx > 25:
            letter_idx = 25 
            
        letter_char = chr(ord('A') + letter_idx)
        tag_str = f"{letter_char}{number:02d}"
        tag_bold = to_math_bold(tag_str)
        
        # Padrão Físico exigido (usando o emoji exato do prompt - Male Sleuth)
        group["new_name"] = f"🕵️‍♂️ 𝗩Λ𝗥𝗥𝗘𝗗𝗨𝗥Λ 𝗚𝗥Λ́𝗧𝗜𝗦 ［#{tag_bold}］ ⚡️ 〘 𝗜Λ 𝗗𝗘𝗧𝗘𝗧𝗜𝗩𝗘 〙"
        
        # Retaura o status se houver, para que os rate-limits não estraguem. Na verdade o mutador
        # lê e ignora as falhas. Mas se mudou o nome, precisamos deixar o status vazio para ele re-mutar o TÍTULO!
        if 'status' in group:
            del group['status']

    # Consolida atômica no disco
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(groups, f, indent=4, ensure_ascii=False)

    logger.info(f"✅ OVERRIDE CONCLUÍDO: {len(groups)} identificadores injetados no banco térmico.")

if __name__ == "__main__":
    apply_names()
