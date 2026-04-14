# config.py

"""
Arquivo de Configuração Centralizado.

Este módulo contém todos os parâmetros operacionais para o bot Vigia e seu
subsistema de análise de conteúdo, o SCTA (Sistema de Classificação Textual Atômica).

A alteração destes valores permite o ajuste fino do comportamento do sistema
sem a necessidade de modificar a lógica de programação principal.

[REVISÃO MESTRA: FUSÃO FINAL SEM PERDAS, COM POTÊNCIA MÁXIMA]
[ATUALIZAÇÃO: Expansão de cobertura para Chinês e fortalecimento dos filtros de RUS/ENG/SPA]
[ATUALIZAÇÃO 3: Implementação de bloqueio para interações casuais em RUS/ENG/SPA/CN]
[ATUALIZAÇÃO 4: INTEGRAÇÃO LETHAL DE SPAM, CONCORRÊNCIA E MEDO]
"""
import re

# --- IMPLEMENTAÇÃO: Filtro de Tolerância Zero ---
# Esta seção define termos que, se detectados, resultarão em banimento imediato
# e permanente, contornando o sistema de avisos progressivos.
# A verificação é feita em minúsculas e busca a correspondência exata da palavra.
INSTANT_BAN_TERMS = {
    # ======================================================================
    # === VIOLAÇÕES DE EXPLORAÇÃO E ABUSO INFANTIL (TOLERÂNCIA ZERO ABSOLUTA) ===
    # ======================================================================
    # PT/ES
    "cp", "pornografia infantil", "abuso infantil", "abuso de menores",
    "estupro infantil",
    # EN
    "child porn", "child abuse", "csam", "child sexual abuse material",
    "minor abuse", "infant porn", "toddler porn",
    # RU
    "детская порнография", "детское порно", "насилие над детьми", "цп",

    # ======================================================================
    # === VIOLAÇÕES DE VIOLÊNCIA EXTREMA E GORE ===
    # ======================================================================
    # PT/ES
    "gore", "esfolamento", "esfolar", "decapitação", "decapitar",
    "desmembramento", "desmembrar", "tortura real", "assassinato real",
    # EN
    "beheading", "decapitation", "dismemberment", "flaying", "real torture",
    "real murder", "snuff",
    # RU
    "расчленение", "обезглавливание", "пытки", "снафф",

    # ======================================================================
    # === PARAFILIAS ILEGAIS E CONTEÚDO DESUMANO ===
    # ======================================================================
    # PT/ES
    "zoofilia", "necrofilia", "bestialidade",
    # EN
    "zoophilia", "necrophilia", "bestiality",
    # RU
    "зоофилия", "некрофилия",

    # ======================================================================
    # === CONTEÚDO RELACIONADO A AUTO-MUTILAÇÃO E SUICÍDIO ===
    # ======================================================================
    # PT/ES
    "cortes nos pulsos", "automutilação", "como se matar", "guia de suicidio",
    # EN
    "self harm", "self-harm", "cutting wrists", "suicide guide", "how to kill yourself",
    # RU
    "самоповреждение", "порезы", "как совершить самоубийство",

    # ======================================================================
    # === DISCURSO DE ÓDIO E TERRORISMO (TERMOS INEQUÍVOCOS) ===
    # ======================================================================
    # PT/ES
    "morte aos judeus", "morte aos negros", "morte aos gays", "heil hitler",
    "supremacia branca", "estado islâmico",
    # EN
    "kill all jews", "kill all blacks", "kill all gays", "white power",
    "white supremacy", "isis", "islamic state",
    # RU
    "смерть евреям", "смерть черным", "белая сила", "игил",
}

# --- Configurações Gerais do Bot (main_vigia.py) ---

DB_FILE = "infractions.db"
# <<< CORREÇÃO: Dicionário de configuração de cooldown restaurado.
# Permite ajuste fino do tempo de "reset" para cada nível de infração.
# A 3ª infração agora tem um ciclo de 60 dias (2 meses) antes de resetar.
COOLDOWN_PERIODS_IN_DAYS = {1: 2, 2: 7, 3: 60}

FORBIDDEN_CONTENT_REGEX = re.compile(
    r'(?:https?://|www\.)\S+|\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b|@\w+',
    re.IGNORECASE
)

# --- Configuração do Motor SCTA (scta_analyzer.py) ---

scta_config = {
    # LIMIAR DE ATIVAÇÃO: Ajustado para 70, um ponto de equilíbrio entre sensibilidade máxima e prevenção de falsos positivos.
    "ACTIVATION_THRESHOLD": 70,

    "LEXICON_NGRAMS": {
        # ======================================================================
        # === SEÇÃO 0: NOVAS CATEGORIAS SOLICITADAS (PESOS ALTO IMPACTO) ===
        # ======================================================================
        
        # --- Categoria: Spam Genérico (Punição Garantida) ---
        "urubu": 100,
        "renda extra": 90,
        "ganhar dinheiro": 90,
        "investimento": 85,
        "crypto": 85,
        "bitcoin": 85,
        "pix": 80,
        "tabela": 80,
        "retorno garantido": 90,
        "plataforma": 75,
        "bug": 75,
        "glitch": 75,
        "sinal": 70,
        "sala de sinais": 80,

        # --- Categoria: Concorrência e Desvio de Tráfego (Punição Garantida) ---
        "telegram.me": 95,
        "t.me": 95,
        "painel": 90,
        "revenda": 90,
        "whatsapp": 85,
        "zap": 85,
        "chat": 80,
        "chama": 80,
        "venda": 75,
        "pv": 75,
        "grupo": 75, # Peso alto: menção única já ativa punição
        "link": 75,  # Peso alto: menção única já ativa punição

        # --- Categoria: Medo e Acusação (Punição Garantida) ---
        "trava": 90,
        "virus": 85,
        "scam": 85,
        "golpe": 85,
        "roubo": 85,
        "ladrão": 85,
        "fake": 80,
        "mentira": 75,
        "policia": 75,
        "ilegal": 75,
        "ban": 75,
        "bloqueio": 75,

        # --- Categoria: Expansão Sexual Massiva (PT-BR Gírias) ---
        "bct": 90, "ppk": 90, "xana": 90, "xota": 90, "bucet": 90,
        "pussy": 90, "priquito": 90, "grelo": 90, "raba": 80, "rabão": 80,
        "dotado": 85, "dotada": 85, "sigilo": 80, "com local": 80, "anal": 85, "oral": 85,
        "inversão": 80, "cam": 80, "videochamada": 80, "gp": 80, "acompanhante": 80,
        "safada": 70, "novinha": 70, "incesto": 100, "estupr": 100,

        # ======================================================================
        # === SEÇÃO 1: LÉXICO ORIGINAL (TUDO MANTIDO INTOCADO) ===
        # ======================================================================

        # --- Sinais de Violação Direta (Conteúdo Adulto / Plataformas) ---
        "porn": 85, "pornô": 85, "pornografia": 85, "hardcore": 80,
        "xxx": 75, "nudes": 75, "onlyfans": 75, "privacy": 75,

        # --- Sinais de Intenção Comercial (Geral) ---
        "tabela de preços": 65,
        "preço no pv": 50,
        "preço no privado": 50,
        "aceito pix": 45,
        "formas de pagamento": 45,
        "envio para todo brasil": 40,
        "loja virtual": 40,
        "visite meu site": 40,
        "promoção": 30,
        "desconto": 30,
        "imperdível": 30,

        # --- Sinais de Alta Intensidade (Conteúdo Adulto) ---
        "vazados": 65, "leaked": 65, "pack do pé": 60, "fotos hot": 60,
        "vídeos hot": 60, "conteúdo adulto": 60, "link na bio": 50,

        # --- Sinais de Média-Alta Intensidade (Contexto de Venda) ---
        "conteúdo no pv": 50, "conteúdo no privado": 50, "meu grupo vip": 45,
        "grupo vip": 45,
        "amostra grátis": 40, "teste grátis": 40,

        # --- Sinais de Média Intensidade (Ação + Produto/Serviço) ---
        "vendo pack": 35, "vendo fotos": 35, "vendo vídeos": 35,
        "vendo curso": 40,
        "vendo conta": 40,
        "conteúdo exclusivo": 30,

        # --- Sinais de Baixa Intensidade (Termos Contextuais) ---
        "vendo": 25,
        "venda": 25,
        "comprar": 20,
        "preço": 15,
        "valor": 15,
        "loja": 15,
        "curso": 15,
        "serviço": 15,
        "pix": 30,
        "pack": 5, "conteúdo": 5, "fotos": 5, "vídeos": 5, "hot": 5,
        "pv": 20, "privado": 15, "vip": 15,

        # ======================================================================
        # === SEÇÃO 2: CAMADA DE REFORÇO (REGRAS EXISTENTES E NOVAS) ===
        # ======================================================================

        # --- NÍVEL 1: TOLERÂNCIA ZERO (Gatilhos de Ativação Imediata - Conteúdo Explícito) ---
        # PT/ES/EN
        "polla": 100, "verga": 100, "pene": 100, "coño": 100, "puta": 100,
        "dick": 100, "cock": 100, "pussy": 100, "bitch": 100, "slut": 100,
        # RU
        "хуй": 100, "пизда": 100, "сука": 100, "блядь": 100, "шлюха": 100,
        "сливы": 85, "слив": 85,
        # CN
        "操你妈": 100, "傻逼": 100, "婊子": 100, "鸡巴": 100, "骚货": 100,

        # --- NÍVEL 1.5: TOLERÂNCIA ZERO (Interações Casuais Indesejadas - Multi-idioma) ---
        # Russo
        "привет": 75, "здравствуйте": 75, "как дела": 75, "доброе утро": 75,
        "добрый день": 75, "добрый вечер": 75, "пока": 75, "до свидания": 75,
        "спасибо": 75, "пожалуйста": 75,
        # Inglês
        "hello": 75, "hi": 75, "hey": 75, "how are you": 75, "good morning": 75,
        "good afternoon": 75, "good evening": 75, "bye": 75, "thanks": 75, "please": 75,
        # Espanhol
        "hola": 75, "qué tal": 75, "buenos días": 75, "buenas tardes": 75,
        "buenas noches": 75, "adiós": 75, "gracias": 75,
        # Chinês
        "你好": 75, "你好吗": 75, "早上好": 75, "下午好": 75, "晚上好": 75,
        "再见": 75, "谢谢": 75, "请": 75,

        # --- NÍVEL 2: REFORÇO DE RIGOR (Expressões Multi-idioma de Alta Intensidade) ---
        # Chamada para Ação Privada (Pesos Elevados)
        "chama no zap": 80, "chama no whats": 80, "chama pv": 80, "vem pv": 80, "vem de pv": 80, "vem pro pv": 80, "me chama": 80, "chama dm": 80, "inbox": 80,
        "vem na dm": 80, "chama no privado": 80, "manda mensagem": 80, "chama no direct": 80, "vem no privado": 80,
        "preço no pv": 80, "preço no privado": 80, "conteúdo no pv": 80,
        "dm for price": 80, "pm for info": 80, "contact me on whatsapp": 80, "message me on whatsapp": 80,
        "escríbeme a whatsapp": 80, "precio por privado": 80, "manda dm": 80, "enviame un dm": 80,
        "пиши в ватсап": 80, "цена в лс": 80, "пишите в директ": 80, "пиши в личку": 80,
        "私聊": 80, "加我微信": 80, "价格私聊": 80, "联系我": 80, "加v": 80,

        # Intenção Comercial Clara (Multi-idioma)
        "price list": 75, "lista de precios": 75, "прайс-лист": 75, "价目表": 75,
        "aceito pix": 75, "we accept crypto": 75, "acepto crypto": 75, "принимаем крипту": 75, "接受加密货币": 75,
        "check my bio": 70, "link in bio": 70, "link en la bio": 70, "ссылка в био": 70, "主页有链接": 70,

        # --- NÍVEL 3: EXPANSÃO CONTEXTUAL (Português, Inglês, Espanhol, Russo e Chinês) ---
        # Reforço Português (Pesos ajustados para maior agressividade)
        "vendo": 65, "venda": 65, "preço": 60, "valor": 60, "pix": 70,
        "comprar": 55, "loja": 50, "curso": 50, "serviço": 50, "pack": 45,
        "conteúdo": 45, "fotos": 45, "vídeos": 45, "hot": 45, "pv": 65,
        "privado": 65, "vip": 60, "conteúdo exclusivo": 60,
        "vendo pack": 70, "vendo fotos": 70, "vendo vídeos": 70,
        "vendo curso": 70, "vendo conta": 70,

        # Expansão Inglês
        "sell": 65, "selling": 65, "for sale": 65, "buy now": 55,
        "price": 60, "shop": 50, "store": 50, "course": 50, "service": 50, "exclusive content": 60,
        "dm": 65, "pm": 65, "private message": 65,

        # Expansão Espanhol
        "vendo": 65, "venta": 65, "en venta": 65, "compra ahora": 55,
        "precio": 60, "tienda": 50, "curso": 50, "servicio": 50, "contenido exclusivo": 60,
        "privado": 65, "vip": 60,

        # Expansão Russo
        "продам": 65, "продажа": 65, "продаю": 65, "купить": 55,
        "цена": 60, "магазин": 50, "курс": 50, "услуга": 50, "эксклюзивный контент": 60,
        "лс": 65, "личку": 65, "вип": 60,

        # Nova Seção: Chinês
        "卖": 65, "出售": 65, "购买": 55, "买": 55,
        "价格": 60, "商店": 50, "课程": 50, "服务": 50, "独家内容": 60,
        "私信": 65, "加微": 70, "福利": 60, "资源": 60, "视频": 45, "照片": 45,
    },

    # PADRÕES ESTRUTURAIS (Originais Mantidos + Universais Adicionados)
    "PATTERNS": {
        # Originais
        r'(-\s|\*\s|•\s).*(r\$|\d{2,})': 60,
        r'\b[a-z]\.[a-z]\.[a-z]\.': 50,
        r'(chama|consulte|pede|solicita|comprar|vem|chamar|chamo|vamos|falem|falar|mandem|manda).*(pv|priv|privado|vip|preço|valor|inbox|dm|direct|zap|whats|whatsapp|telegram)': 85,

        # Adições Universais
        r'(contact|dm|pm|ask|buy|escribe|compra|пиши|купить|私聊|联系).*(price|direct|private|precio|лс|директ|价格|微信)': 80,
        r'(-\s|\*\s|•\s).*(usd|eur|rub|ars|cny|¥)': 75,
        r'\b[a-zа-я]\.[a-zа-я]\.[a-zа-я]\.': 70,
        
        # --- BLOQUEIO DE SCRIPT NÃO-LATINO (TOLERÂNCIA ZERO) ---
        # Detecta caracteres Chineses (CJK), Cirílicos, Árabes e Devanágari.
        # Qualquer match resulta em pontuação +100 (Violação Imediata).
        r'[\u4e00-\u9fff\u0400-\u04ff\u0600-\u06ff\u0900-\u097f]': 100,

        # --- PADRÕES DE OFUSCAÇÃO ---
        # Detecta espaçamento forçado ou com pontos (s e x o, p.0.r.n, b.c.t)
        r'\b(s[\s\.]*e[\s\.]*x[\s\.]*o|p[\s\.]*[o0][\s\.]*r[\s\.]*n|b[\s\.]*c[\s\.]*t|p[\s\.]*p[\s\.]*k)\b': 100,
        # Detecta substituição simples (leetspeak)
        r'\b(p0rn|s3xo|pr0n)\b': 90,
    },

    # PESOS DE EMOJIS (Agressividade Aumentada e Novos Emojis)
    "EMOJI_WEIGHTS": {
        "🔞": 35, "😈": 25, "💦": 25, "🔥": 20, "😏": 20,
        "🍑": 15, "🍆": 15, "💸": 30, "💰": 30, "🤑": 30,
        "👉": 15, "👇": 15, "🛍️": 25, "🛒": 25, "🧧": 25, "㊗️": 25,
    }
}