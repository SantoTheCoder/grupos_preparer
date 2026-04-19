import json

def main():
    try:
        with open('data/groups.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print("Erro ao ler JSON:", e)
        return

    with open('saida_tabela.md', 'w', encoding='utf-8') as out:
        out.write("### 🟡 Delta (031 a 040) [VPS 7]\n")
        out.write("| Nó Operacional | ID do Grupo | Alvo / Referência | Link (GRUPO_LINK) |\n")
        out.write("|:---|:---|:---|:---|\n")
        
        for g in data:
            nome = g.get('node_operacional', '')
            if not nome.startswith('bot_'):
                continue
                
            try:
                num = int(nome.split('_')[1])
            except:
                continue
                
            if 31 <= num <= 65:
                if num == 41:
                    out.write("\n### 🟢 Epsilon (041 a 050) [VPS 8]\n")
                    out.write("| Nó Operacional | ID do Grupo | Alvo / Referência | Link (GRUPO_LINK) |\n")
                    out.write("|:---|:---|:---|:---|\n")
                elif num == 51:
                    out.write("\n### 🔵 Zeta (051 a 060) [VPS 9]\n")
                    out.write("| Nó Operacional | ID do Grupo | Alvo / Referência | Link (GRUPO_LINK) |\n")
                    out.write("|:---|:---|:---|:---|\n")
                elif num == 61:
                    out.write("\n### 🟣 Eta (061 a 065) [VPS 10]\n")
                    out.write("| Nó Operacional | ID do Grupo | Alvo / Referência | Link (GRUPO_LINK) |\n")
                    out.write("|:---|:---|:---|:---|\n")
                    
                # Procura a chave certa
                link = g.get('invite_link') or g.get('group_link') or g.get('link') or "Sem Link"
                out.write(f"| **`{nome}`** | `{g.get('group_id')}` | {g.get('group_name')} | `{link}` |\n")

if __name__ == '__main__':
    main()
