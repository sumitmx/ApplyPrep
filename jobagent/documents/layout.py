"""One type scale and spacing rhythm, shared by all three CV renderers.

The DOCX, the PDF and the on-screen preview used to carry their own numbers,
which is why an export never quite looked like the preview - the role header,
for instance, was 11pt in Word and 9.5pt in the PDF. Everything now reads from
here, so the three can only drift if this file changes.

Sizes are in points because that is the unit both Word and the PDF think in.
The browser gets the same numbers converted to CSS pixels.
"""

# 1pt = 1/72in, 1 CSS px = 1/96in.
PT_TO_PX = 96.0 / 72.0

FONT_PT = {
    "name": 22,
    "headline": 10.5,
    "contact": 9,
    "heading": 12,
    "body": 9.5,
    # The role line is the anchor of the experience section: it has to read as
    # a clear step above the bullets underneath it, so employers stay scannable.
    "role": 11.5,
    "client": 9,
    "meta": 8.5,
    # Deliberately three points under "role". Bullets are supporting detail and
    # should not compete with the company name for attention.
    "bullet": 8.5,
}

SPACE_PT = {
    "section_before": 14,   # air above each section heading
    "section_after": 6,     # heading down to its first line
    "section_end": 8,       # last line of a section down to the next heading
    "role_before": 10,      # air between one employer and the next
    "role_after": 1,        # role line down to client/location
    "meta_after": 3,        # location line down to the first bullet
    "bullet_after": 2,      # between bullets
    "bullets_after": 4,     # last bullet down to whatever follows
    "para_after": 3,
}


def css_vars():
    """The same scale as CSS custom properties, for the preview."""
    out = {}
    for key, pt in FONT_PT.items():
        out["--cv-fs-" + key] = str(round(pt * PT_TO_PX, 2)) + "px"
    for key, pt in SPACE_PT.items():
        out["--cv-sp-" + key.replace("_", "-")] = str(round(pt * PT_TO_PX, 2)) + "px"
    return out
