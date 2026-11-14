"""Free, offline drafts from JMdict (word readings + English glosses) and
KANJIDIC2 (per-kanji on/kun readings). Claude only fills in what these can't:
the Japanese definition, the example sentence and the Japanese kanji glosses."""
import os
import shutil

import jamdict_data
from jamdict import Jamdict

# The 325 MB dictionary ships inside the venv on the Windows drive, where SQLite
# reads from WSL are very slow. Copy it once onto the Linux filesystem.
_SRC_DB = os.path.join(os.path.dirname(jamdict_data.__file__), "jamdict.db")
_LOCAL_DB = os.path.expanduser("~/.cache/jamdict/jamdict.db")

MAX_ON = 2
MAX_KUN = 2
MAX_GLOSSES = 6


def kata_to_hira(s):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def is_kanji(c):
    return "一" <= c <= "鿿" or c == "々"


def _pick(candidates, matches, limit):
    """Keep readings that occur in the word's reading, then fill up to `limit`
    with the rest, preserving the dictionary's own order."""
    chosen = [c for c in candidates if matches(c)]
    for c in candidates:
        if len(chosen) >= limit:
            break
        if c not in chosen:
            chosen.append(c)
    return [c for c in candidates if c in chosen]


def _kanji_draft(char, reading):
    rm = char.rm_groups[0] if char.rm_groups else None
    if rm is None:
        return {"char": char.literal, "on": [], "kun": [], "meanings_en": []}
    ons = [r.value for r in rm.on_readings if "-" not in r.value]
    kuns = []
    for r in rm.kun_readings:
        v = r.value
        if "-" in v:
            continue
        stem, _, okuri = v.partition(".")
        fmt = f"{stem}({okuri})" if okuri else stem
        if fmt not in [k for k, _ in kuns]:
            kuns.append((fmt, stem))
    stems = dict(kuns)
    on = _pick(ons, lambda o: kata_to_hira(o) in reading, MAX_ON)
    kun_fmt = _pick(list(stems), lambda k: stems[k] in reading, MAX_KUN)
    meanings = [m.value for m in rm.meanings if m.m_lang in ("", "en")][:3]
    return {"char": char.literal, "on": on, "kun": kun_fmt, "meanings_en": meanings}


def _best_entry(entries, word):
    exact = [e for e in entries if any(k.text == word for k in e.kanji_forms)
             or any(k.text == word for k in e.kana_forms)]
    pool = exact or entries
    # Prefer entries marked as common (ichi1/news1/... priority tags).
    pool.sort(key=lambda e: not any(k.pri for k in e.kanji_forms + e.kana_forms))
    return pool[0] if pool else None


def _best_reading(entry):
    kana = [k for k in entry.kana_forms if k.text != "の"]
    hira = [k for k in kana if kata_to_hira(k.text) == k.text] or kana
    hira.sort(key=lambda k: not k.pri)
    return hira[0].text if hira else ""


def lookup_many(words):
    """Draft data for each word. Words the dictionary doesn't know come back
    with empty fields for Claude to fill in."""
    if not os.path.exists(_LOCAL_DB):
        os.makedirs(os.path.dirname(_LOCAL_DB), exist_ok=True)
        shutil.copyfile(_SRC_DB, _LOCAL_DB + ".tmp")
        os.replace(_LOCAL_DB + ".tmp", _LOCAL_DB)
    jam = Jamdict(db_file=_LOCAL_DB, kd2_file=_LOCAL_DB)
    out = []
    for word in words:
        res = jam.lookup(word, strict_lookup=True, lookup_chars=True)
        entry = _best_entry(list(res.entries), word)
        reading = _best_reading(entry) if entry else ""
        glosses = [g.text for s in entry.senses for g in s.gloss][:MAX_GLOSSES] if entry else []
        chars = {c.literal: c for c in res.chars}
        kanji = [_kanji_draft(chars[ch], reading) for ch in dict.fromkeys(word)
                 if is_kanji(ch) and ch in chars]
        out.append({
            "word": word,
            "reading": reading,
            "glosses_en": glosses,
            "kanji": kanji,
            "in_dictionary": entry is not None,
        })
    return out
