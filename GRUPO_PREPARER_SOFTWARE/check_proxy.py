import json

try:
    with open('data/accounts.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print("Contas encontradas:")
    for a in data:
        proxy = a.get('proxy')
        if proxy:
            print(f"- Phone: {a.get('phone')} | Proxy: {proxy}")
        else:
            print(f"- Phone: {a.get('phone')} | Sem proxy no JSON")
            
except Exception as e:
    print("Erro", e)
