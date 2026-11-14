"""Getting cards into Anki: AnkiConnect push, with a .txt + media-copy fallback.

Never writes to collection.anki2 directly. The only direct read is of a temp
copy, to tell which words are already in the deck while Anki is closed.
"""
import base64
import os
import shutil
import sqlite3
import tempfile

import requests

from pipeline import render


class AnkiError(Exception):
    pass


class Anki:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = cfg["ankiconnect_url"]

    # -- AnkiConnect ---------------------------------------------------------
    def invoke(self, action, _timeout=10, **params):
        try:
            r = requests.post(self.url, json={"action": action, "version": 6, "params": params}, timeout=_timeout)
        except requests.RequestException as e:
            raise AnkiError(f"AnkiConnect not reachable at {self.url} (is Anki open with AnkiConnect installed?)") from e
        try:
            body = r.json()
        except ValueError as e:
            raise AnkiError(f"Something other than AnkiConnect is answering at {self.url} "
                            "(check AnkiConnect's webBindPort matches config.json)") from e
        if body.get("error"):
            raise AnkiError(f"{action}: {body['error']}")
        return body["result"]

    def available(self):
        try:
            return self.invoke("version", _timeout=2) >= 6
        except AnkiError:
            return False

    # -- duplicates ----------------------------------------------------------
    def existing_words(self, words):
        """Which of `words` already exist as a Front in the note type.
        Uses AnkiConnect if Anki is open, else a temp copy of the collection."""
        if self.available():
            found = set()
            for w in words:
                q = f'"note:{self.cfg["notetype"]}" "{self.cfg["front_field"]}:{_escape(w)}"'
                if self.invoke("findNotes", query=q):
                    found.add(w)
            return found
        return set(words) & self._fronts_from_collection_copy()

    def _fronts_from_collection_copy(self):
        src = os.path.join(self.cfg["anki_profile_dir"], "collection.anki2")
        if not os.path.exists(src):
            return set()
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ("", "-wal"):
                if os.path.exists(src + suffix):
                    shutil.copyfile(src + suffix, os.path.join(tmp, "c.anki2" + suffix))
            db = sqlite3.connect(os.path.join(tmp, "c.anki2"))
            # Anki's schema declares this collation; SQLite needs it to query names.
            db.create_collation("unicase", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
            try:
                rows = db.execute(
                    "select n.flds from notes n join notetypes t on t.id = n.mid where t.name = ?",
                    (self.cfg["notetype"],)).fetchall()
            finally:
                db.close()
        return {flds.split("\x1f")[0] for (flds,) in rows}

    # -- push ----------------------------------------------------------------
    def push(self, cards, image_paths):
        """Store each card's image, then add the note. Returns (added, failed)
        where failed is [(card, reason)]. Cards are sent one at a time so one bad
        card can't block the rest."""
        added, failed = [], []
        for card in cards:
            try:
                path = image_paths.get(card["word"])
                if path:
                    with open(path, "rb") as f:
                        data = base64.b64encode(f.read()).decode()
                    # deleteExisting=False: never overwrite an existing media file;
                    # Anki returns the (possibly renamed) filename to reference.
                    card = {**card, "image": self.invoke(
                        "storeMediaFile", filename=card["image"], data=data, deleteExisting=False)}
                self.invoke("addNote", note={
                    "deckName": self.cfg["deck"],
                    "modelName": self.cfg["notetype"],
                    "fields": {self.cfg["front_field"]: render.render_front(card),
                               self.cfg["back_field"]: render.render_back(card)},
                    "options": {"allowDuplicate": False},
                    "tags": self.cfg["tags"],
                })
                added.append(card)
            except AnkiError as e:
                failed.append((card, str(e)))
        return added, failed

    # -- fallback ------------------------------------------------------------
    def fallback(self, cards, image_paths, out_txt):
        """Write an import file and copy images into collection.media (skipping
        any filename that already exists there)."""
        with open(out_txt, "w", encoding="utf-8") as f:
            f.write(render.to_txt(cards, self.cfg["deck"], self.cfg["notetype"]))
        media = os.path.join(self.cfg["anki_profile_dir"], "collection.media")
        copied, skipped = [], []
        for card in cards:
            path = image_paths.get(card["word"])
            if not path:
                continue
            dest = os.path.join(media, card["image"])
            if os.path.exists(dest):
                skipped.append(card["image"])
            else:
                shutil.copyfile(path, dest)
                copied.append(card["image"])
        return copied, skipped


def _escape(word):
    # Anki search syntax: escape the characters that have special meaning.
    for ch in '\\"*_:':
        word = word.replace(ch, "\\" + ch)
    return word
