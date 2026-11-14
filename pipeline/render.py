"""Render cards in the exact format of the user's existing Anki deck.

The format was derived from the 379 notes already in the collection (all of them
share it): the front is the bare word, and the back is a fixed sequence of
styled divs. Keep these strings byte-identical; the deck relies on them.

A card is a dict:
    word        str   front of the card
    reading     str   kana reading
    definition  str   Japanese definition
    example     str   Japanese example sentence
    image       str   media filename, e.g. "呼応.png" ("" = no image)
    kanji       list  [{"char", "on": [...], "kun": [...], "gloss"}]
    kanji_custom str  raw HTML used *instead of* kanji lines (ateji etc.), optional
    en_hint     str   optional short English hint
"""
import csv
import io

READING = '<div style="font-size:1.3em;font-weight:bold;margin-bottom:6px;">{}</div>'
DEFINITION = '<div style="margin-bottom:10px;">{}</div>'
EXAMPLE = ('<div style="background:#f5f3ee;border-left:3px solid #ccc;padding:8px 12px;'
           'margin-bottom:14px;border-radius:0 2px 2px 0;"><div style="font-size:0.95em;">{}</div></div>')
IMAGE = '<div style="text-align:center;margin:8px 0;"><img src="{}"></div>'
KANJI_BLOCK = '<hr><div style="font-size:0.95em;color:#555;">{}</div>'
EN_HINT = '<div style="font-size:0.8em;color:#999;font-style:italic;margin-top:8px;">{}</div>'

REQUIRED = ("word", "reading", "definition", "example")
FORBIDDEN = ("\t", "\n", "\r", "\x1f")  # would corrupt the note / import row


def kanji_line(k):
    parts = []
    if k.get("on"):
        parts.append("音 " + "・".join(k["on"]))
    if k.get("kun"):
        parts.append("訓 " + "・".join(k["kun"]))
    return f'<b>{k["char"]}</b> ({"／".join(parts)}) — {k["gloss"]}'


def render_front(card):
    return card["word"]


def render_back(card):
    out = [
        READING.format(card["reading"]),
        DEFINITION.format(card["definition"]),
        EXAMPLE.format(card["example"]),
    ]
    if card.get("image"):
        out.append(IMAGE.format(card["image"]))
    if card.get("kanji_custom"):
        block = card["kanji_custom"]
    else:
        block = "<br>".join(kanji_line(k) for k in card.get("kanji", []))
    out.append(KANJI_BLOCK.format(block))
    if card.get("en_hint"):
        out.append(EN_HINT.format(card["en_hint"]))
    return "".join(out)


def validate(card):
    """Return a list of problems with a card (empty list = OK)."""
    problems = [f"missing {f}" for f in REQUIRED if not card.get(f)]
    if not card.get("kanji") and not card.get("kanji_custom"):
        problems.append("no kanji breakdown")
    for k in card.get("kanji", []):
        if not k.get("char") or not k.get("gloss") or not (k.get("on") or k.get("kun")):
            problems.append(f"incomplete kanji entry {k.get('char', '?')}")
    for ch in FORBIDDEN:
        if any(ch in s for s in _strings(card)):
            problems.append(f"contains forbidden character {ch!r}")
    return problems


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def to_txt(cards, deck, notetype="Basic"):
    """Anki import file: tab-separated, CSV-quoted, with headers that preselect
    the note type and deck in Anki's import dialog."""
    buf = io.StringIO()
    buf.write("#separator:tab\n#html:true\n")
    buf.write(f"#notetype:{notetype}\n#deck:{deck}\n")
    w = csv.writer(buf, delimiter="\t", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    for c in cards:
        w.writerow([render_front(c), render_back(c)])
    return buf.getvalue()
