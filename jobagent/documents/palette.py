"""CV accent colors, and the text color that stays readable on each one.

Accents come in two tones. "deep" carries white text; "light" is washed out
enough that white would disappear, so it carries dark ink instead. Rather than
hardcoding that pairing per color, ink_for() measures the accent and picks
whichever gives better contrast - so a new accent added here needs no changes
anywhere else.
"""

WHITE = "#FFFFFF"
DARK_INK = "#1F2933"

ACCENTS = {
    # Deep tones - white text sits on these.
    "navy": {"label": "Navy", "hex": "#1F3864", "tone": "deep"},
    "slate": {"label": "Slate", "hex": "#2E5496", "tone": "deep"},
    "charcoal": {"label": "Charcoal", "hex": "#33383D", "tone": "deep"},
    "forest": {"label": "Forest", "hex": "#2F5D3A", "tone": "deep"},
    "burgundy": {"label": "Burgundy", "hex": "#7A2734", "tone": "deep"},
    "teal": {"label": "Teal", "hex": "#1F6B66", "tone": "deep"},
    # Light tones - dark ink sits on these.
    "sky": {"label": "Sky", "hex": "#8FB8E0", "tone": "light"},
    "sage": {"label": "Sage", "hex": "#9CBFA6", "tone": "light"},
    "sand": {"label": "Sand", "hex": "#DCC08A", "tone": "light"},
    "blush": {"label": "Blush", "hex": "#E0A9A0", "tone": "light"},
    "lilac": {"label": "Lilac", "hex": "#B3A9DA", "tone": "light"},
    "mist": {"label": "Mist", "hex": "#B8C4CE", "tone": "light"},
}

DEFAULT_ACCENT = "navy"


def _channel(value):
    """One sRGB channel, linearised for the luminance formula."""
    c = value / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_value):
    """WCAG relative luminance, 0 (black) to 1 (white)."""
    h = str(hex_value or "").lstrip("#")
    if len(h) != 6:
        return 0.0
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(hex_a, hex_b):
    """WCAG contrast ratio between two colors, 1.0 to 21.0."""
    light, dark = sorted((luminance(hex_a), luminance(hex_b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def ink_for(hex_value):
    """The more readable of white or dark ink on the given background."""
    if contrast(hex_value, WHITE) >= contrast(hex_value, DARK_INK):
        return WHITE
    return DARK_INK


def resolve(key):
    entry = ACCENTS.get(key, ACCENTS[DEFAULT_ACCENT])
    return {**entry, "ink": ink_for(entry["hex"])}


def on_paper(hex_value, minimum=4.5):
    """A version of the accent dark enough to read as text on white paper.

    Deep accents come back untouched. Light ones (Sand, Blush) would sit at
    around 1.7:1 against white, so they are stepped down until they clear the
    WCAG AA threshold - keeping the hue while making the text legible.
    """
    h = str(hex_value or "").lstrip("#")
    if len(h) != 6:
        return hex_value
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    for _ in range(40):
        current = "#%02X%02X%02X" % tuple(rgb)
        if contrast(current, WHITE) >= minimum:
            return current
        rgb = [max(0, int(c * 0.92)) for c in rgb]
    return "#%02X%02X%02X" % tuple(rgb)
