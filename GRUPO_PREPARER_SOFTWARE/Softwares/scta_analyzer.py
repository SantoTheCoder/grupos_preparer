# scta_analyzer.py

"""
Módulo de Análise para o Sistema de Classificação Textual Atômica (SCTA).

Este módulo fornece uma função stateless para analisar o conteúdo textual de uma
mensagem e retornar uma pontuação de violação baseada em um conjunto de
heurísticas ponderadas. A lógica é puramente determinística e não depende de
estado externo ou histórico.

A sensibilidade do analisador é controlada através de um dicionário de
configuração importado do módulo `config.py`.
"""

import re
from typing import Dict, Any

# A importação da configuração é a única dependência externa deste módulo.
# Isso permite que toda a lógica de negócio seja ajustada sem tocar neste arquivo.
try:
    from config import scta_config
except ImportError:
    # Fornece uma configuração padrão caso o arquivo config.py não exista,
    # garantindo que o módulo não falhe na importação, embora com funcionalidade limitada.
    scta_config: Dict[str, Any] = {
        "ACTIVATION_THRESHOLD": 100,
        "LEXICON_NGRAMS": {},
        "PATTERNS": {},
        "EMOJI_WEIGHTS": {}
    }

def _normalize_text(text: str) -> str:
    """
    Prepara o texto para análise, convertendo para minúsculas e aplicando
    normalizações básicas para facilitar a correspondência de padrões.
    """
    return text.lower()

def _calculate_lexical_score(normalized_text: str) -> int:
    """
    Calcula a pontuação baseada na presença de termos e combinações de termos
    (N-gramas) definidos no léxico de configuração. Termos mais longos e mais
    específicos devem ter pesos maiores.
    """
    score = 0
    lexicon: Dict[str, int] = scta_config.get("LEXICON_NGRAMS", {})
    
    # Ordena o léxico pelo comprimento da chave em ordem decrescente para garantir
    # que N-gramas mais longos (ex: "vendo fotos") sejam correspondidos antes
    # de seus componentes mais curtos (ex: "fotos").
    for term, weight in sorted(lexicon.items(), key=lambda item: len(item[0]), reverse=True):
        occurrences = normalized_text.count(term)
        if occurrences > 0:
            score += occurrences * weight
            # Remove o termo encontrado para evitar contagem dupla por sub-termos.
            # Ex: após pontuar "vendo fotos", removemos para não pontuar "fotos" isoladamente.
            normalized_text = normalized_text.replace(term, "")
            
    return score

def _calculate_structural_score(normalized_text: str) -> int:
    """
    Calcula a pontuação baseada em padrões estruturais e de intenção,
    utilizando expressões regulares definidas na configuração.
    Isso captura "formas" de texto, como CTAs e ofuscação.
    """
    score = 0
    patterns: Dict[str, int] = scta_config.get("PATTERNS", {})
    
    for pattern, weight in patterns.items():
        # re.IGNORECASE já é tratado pela normalização para minúsculas.
        # re.VERBOSE pode ser útil para padrões complexos na configuração.
        if re.search(pattern, normalized_text):
            score += weight
            
    return score

def _calculate_emoji_score(text: str) -> int:
    """
    Calcula a pontuação baseada na contagem de emojis específicos que atuam como
    intensificadores de intenção. A análise é feita no texto original para
    evitar problemas com a normalização.
    """
    score = 0
    emoji_weights: Dict[str, int] = scta_config.get("EMOJI_WEIGHTS", {})
    
    for emoji, weight in emoji_weights.items():
        score += text.count(emoji) * weight
        
    return score

def analyze_message_score(text: str) -> int:
    """
    Orquestra o processo de análise completo e retorna a pontuação final.

    Args:
        text: O conteúdo textual bruto da mensagem a ser analisada.

    Returns:
        A pontuação de violação total calculada para a mensagem.
    """
    if not text or not isinstance(text, str):
        return 0

    # O texto original é passado para a análise de emojis.
    emoji_score = _calculate_emoji_score(text)

    # O texto normalizado é usado para análises lexicais e estruturais.
    normalized_text = _normalize_text(text)
    lexical_score = _calculate_lexical_score(normalized_text)
    structural_score = _calculate_structural_score(normalized_text)
    
    total_score = lexical_score + structural_score + emoji_score
    return total_score

def is_violation(text: str) -> bool:
    """
    Função de interface pública que retorna uma decisão booleana simples.
    Este é o ponto de entrada principal para o `main_vigia.py`.

    Args:
        text: O conteúdo textual bruto da mensagem a ser analisada.

    Returns:
        True se a pontuação da mensagem atingir ou exceder o limiar de
        ativação, False caso contrário.
    """
    threshold = int(scta_config.get("ACTIVATION_THRESHOLD", 100))
    score = analyze_message_score(text)
    
    # A decisão final é uma comparação simples, tornando o resultado inequívoco.
    return score >= threshold