"""Lightweight, dependency-free language detection for short chat messages.

Only needs to pick among the small set of languages a given business has
actually enabled (see AVAILABLE_LANGUAGES in SettingsPage.tsx) -- not
perform open-set language ID -- so a character/stopword scoring heuristic
is plenty, and keeps this in sync with what the LLM is separately asked to
detect (see language_instruction in rag/providers/base.py), rather than
depending on the visitor's browser locale, which has no relationship to
what they're actually typing.
"""
import re
from typing import List

_SIGNALS = {
    "no": {"chars": "æøå", "words": {
        "jeg", "du", "er", "og", "ikke", "hva", "hvor", "kan", "deres", "dere",
        "reservere", "bord", "gruppe", "stor", "takk", "hei", "vil", "har", "til",
    }},
    "de": {"chars": "äöüß", "words": {
        "ich", "und", "ist", "sie", "wie", "wo", "kann", "nicht", "der", "die",
        "das", "danke", "hallo", "bitte", "haben",
    }},
    "fr": {"chars": "àâçéèêëîïôûùü", "words": {
        "je", "vous", "est", "le", "la", "les", "comment", "où", "merci",
        "bonjour", "avez", "pouvez",
    }},
    "es": {"chars": "ñ¿¡", "words": {
        "el", "la", "los", "las", "cómo", "dónde", "puedo", "está", "gracias",
        "hola", "tienen", "quiero",
    }},
    "it": {"chars": "", "words": {
        "il", "lo", "gli", "sono", "come", "dove", "posso", "grazie", "ciao",
        "avete", "vorrei",
    }},
    "nl": {"chars": "", "words": {
        "ik", "je", "is", "en", "hoe", "waar", "kan", "niet", "jullie", "dank",
        "hallo", "hebben",
    }},
    "pl": {"chars": "ąćęłńóśźż", "words": {
        "jest", "czy", "jak", "gdzie", "mogę", "nie", "dziękuję", "cześć", "macie",
    }},
    "pt": {"chars": "ãõáéíóúâêôç", "words": {
        "você", "como", "onde", "posso", "está", "não", "obrigado", "olá", "têm",
    }},
    "sv": {"chars": "åäö", "words": {
        "jag", "är", "och", "hur", "var", "kan", "inte", "ni", "tack", "hej", "har",
    }},
    "en": {"chars": "", "words": {
        "the", "is", "are", "you", "and", "what", "where", "how", "can", "do",
        "please", "thanks", "hello", "have", "want",
    }},
}

_WORD_RE = re.compile(r"[a-zæøåäöüßàâçéèêëîïôûùüñ¿¡ąćęłńśźżãõáíóúâêô]+")


def detect_message_language(message: str, candidates: List[str], default: str) -> str:
    """Scores `message` against each candidate's distinctive characters/stopwords
    and returns the best match. Falls back to `default` when nothing scores --
    a confident wrong guess is worse than a predictable default here, since this
    also picks the fallback_messages translation directly (no LLM involved)."""
    if not candidates:
        return default
    if len(candidates) == 1:
        return candidates[0]

    lowered = message.lower()
    words = set(_WORD_RE.findall(lowered))

    scores = {}
    for code in candidates:
        signal = _SIGNALS.get(code)
        if not signal:
            continue
        score = sum(1 for ch in signal["chars"] if ch in lowered)
        score += len(words & signal["words"])
        scores[code] = score

    if not scores:
        return default
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else default
