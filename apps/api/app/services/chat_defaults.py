"""Built-in chat widget texts, written per language rather than machine-translated.

QA 2026-10-08 (W-06): the default fallback's machine translation read
"Vil du tale med vår team?" (wrong word, wrong gender), and a visitor who
wanted to buy got that "I'm not sure" reply before the lead form.
"""

DEFAULT_WELCOME_MESSAGE = "Hi! How can I help you today?"
DEFAULT_FALLBACK_MESSAGE = "I'm not sure about that. Would you like to speak with our team?"

# The defaults above in the other languages, used instead of an LLM translation
# while the owner still has the default English text.
DEFAULT_TRANSLATIONS = {
    DEFAULT_WELCOME_MESSAGE: {
        "no": "Hei! Hva kan jeg hjelpe deg med i dag?",
    },
    DEFAULT_FALLBACK_MESSAGE: {
        "no": "Det er jeg ikke sikker på. Vil du snakke med teamet vårt?",
    },
}

# Reply to a contact/buying question that the knowledge base can't answer (no
# contact details in Settings, nothing retrieved). The widget shows the lead
# form under it, so it invites the visitor to fill it in rather than saying
# "I'm not sure".
LEAD_PROMPTS = {
    "en": "Happy to help! Leave your contact details below and our team will get back to you.",
    "no": "Gjerne! Legg igjen kontaktinformasjonen din nedenfor, så tar teamet vårt kontakt med deg.",
    "de": "Gerne! Hinterlassen Sie unten Ihre Kontaktdaten, dann meldet sich unser Team bei Ihnen.",
    "fr": "Avec plaisir ! Laissez vos coordonnées ci-dessous et notre équipe vous recontactera.",
    "es": "¡Con gusto! Deja tus datos de contacto abajo y nuestro equipo se pondrá en contacto contigo.",
    "it": "Volentieri! Lascia i tuoi dati di contatto qui sotto e il nostro team ti ricontatterà.",
    "nl": "Graag! Laat hieronder je contactgegevens achter, dan neemt ons team contact met je op.",
    "pl": "Chętnie pomożemy! Zostaw poniżej swoje dane kontaktowe, a nasz zespół się z Tobą skontaktuje.",
    "pt": "Com todo o gosto! Deixe os seus dados de contacto abaixo e a nossa equipa entrará em contacto consigo.",
    "sv": "Gärna! Lämna dina kontaktuppgifter nedan så hör vårt team av sig till dig.",
}


def default_translation(source_text: str, lang: str) -> str | None:
    """The built-in `lang` version of a default text, or None (translate it)."""
    return DEFAULT_TRANSLATIONS.get(source_text, {}).get(lang)


def lead_prompt(lang: str) -> str:
    return LEAD_PROMPTS.get(lang, LEAD_PROMPTS["en"])
