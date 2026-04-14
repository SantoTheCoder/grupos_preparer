import json
import os
import time
import logging

logger = logging.getLogger("ESTADO_MATRIZ")

class StateMachine:
    """
    Rastreador O(1) de Execução Isolada. 
    Protege a continuidade do sistema (Zero Retrabalho) contra desligamentos de hardware
    e efetua o controle atômico termal (Anti-SPAM) separado por Pessoa/Owner.
    """
    def __init__(self, db_path="data/database_grupos.json", state_path="data/migration_state.json"):
        self.db_path = db_path
        self.state_path = state_path
        self.state = self._load_or_initialize()

    def _load_or_initialize(self) -> dict:
        """Carrega a esteira do disco ou projeta o esquema inicial a partir da base pura."""
        if os.path.exists(self.state_path):
            with open(self.state_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Base matricial não detectada em {self.db_path}. Abortando.")

        with open(self.db_path, 'r', encoding='utf-8') as f:
            base_db = json.load(f)
            
        initial_state = {}
        for group in base_db:
            if not group.get("is_mapped"):
                continue # Evade entropia: Ignora nós fantasmas inalcançáveis
                
            owner = group.get("owner")
            # Construtor da Pessoa O(1)
            if owner not in initial_state:
                initial_state[owner] = {
                    "tg_node": group.get("tg_node"),
                    "status": "LIVRE", # LIVRE, FLOODWAIT, ESVAZIADO
                    "flood_wait_until": 0.0,
                    "groups": {}
                }
            
            # Construtor do Fardo do Grupo Específico
            initial_state[owner]["groups"][str(group.get("id"))] = {
                "link": group.get("link_convite", ""),
                "internal_code": group.get("internal_code", ""),
                "actions": {
                    "clear_history": "PENDENTE",
                    "change_name": "PENDENTE",
                    "change_desc": "PENDENTE",
                    "change_photo": "PENDENTE",
                    "support_post": "PENDENTE",
                    "owner_pin": "PENDENTE"
                }
            }
            
        self._commit(initial_state)
        logger.info(f"🔰 Arvore de Estados Puros alocada. {len(initial_state)} Pessoas enfileiradas.")
        return initial_state

    def _commit(self, data_override=None):
        """Bloqueio atômico em disco. Imutabilidade até o próximo ciclo."""
        out = data_override if data_override else self.state
        with open(self.state_path, 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=4, ensure_ascii=False)

    def is_person_free(self, person: str) -> bool:
        """Matemática de Barramento: Verifica se a pessoa não está em prisão térmica (Spam)."""
        p_data = self.state.get(person)
        if not p_data: return False
        
        if p_data["status"] == "FLOODWAIT":
            if time.time() > p_data["flood_wait_until"]:
                p_data["status"] = "LIVRE"
                p_data["flood_wait_until"] = 0.0
                self._commit()
                return True
            return False
            
        return p_data["status"] == "LIVRE"

    def apply_thermal_block(self, person: str, seconds: int):
        """Ejeta a pessoa atual do ciclo impondo latência rígida de proteção."""
        if person in self.state:
            self.state[person]["status"] = "FLOODWAIT"
            self.state[person]["flood_wait_until"] = time.time() + float(seconds)
            self._commit()
            logger.warning(f"⏳ BLOQUEIO TERMÁLICO ATIVO O(1): Pessoa [{person}] travada por {seconds}s. Pulando proxeção.")

    def get_action_status(self, person: str, group_id: str, action_key: str) -> str:
        """Checagem assintótica O(1) de estado (Previne redundância de ações já FEITAS)."""
        try:
            return self.state[person]["groups"][str(group_id)]["actions"][action_key]
        except KeyError:
            return "PENDENTE"

    def mark_action_done(self, person: str, group_id: str, action_key: str):
        """Anota a operação física como executada no disco."""
        if person in self.state and str(group_id) in self.state[person]["groups"]:
            self.state[person]["groups"][str(group_id)]["actions"][action_key] = "FEITO"
            self._commit()

    def get_next_person(self) -> str:
        """Retorna a próxima pessoa Livre, que ainda tenha grupos a processar."""
        for person_name, data in self.state.items():
            if self.is_person_free(person_name):
                # Checa se ela tem alguma ação pendente em algum grupo
                has_pending = False
                for g_id, g_data in data["groups"].items():
                    if any(val == "PENDENTE" for val in g_data["actions"].values()):
                        has_pending = True
                        break
                
                if has_pending:
                    return person_name
                else:
                    data["status"] = "ESVAZIADO" # Marcou conta como 100% ok
                    self._commit()
        return None
