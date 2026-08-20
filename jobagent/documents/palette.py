ACCENTS = {
    "navy": {"label": "Navy", "hex": "#1F3864"},
    "slate": {"label": "Slate", "hex": "#2E5496"},
    "charcoal": {"label": "Charcoal", "hex": "#33383D"},
    "forest": {"label": "Forest", "hex": "#2F5D3A"},
    "burgundy": {"label": "Burgundy", "hex": "#7A2734"},
    "teal": {"label": "Teal", "hex": "#1F6B66"},
}

DEFAULT_ACCENT = "navy"


def resolve(key):
    return ACCENTS.get(key, ACCENTS[DEFAULT_ACCENT])
