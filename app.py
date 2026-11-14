"""Sheets → Anki: local web app for the flashcard pipeline.

Run with start_app.bat (or: venv/bin/streamlit run app.py). Each run lives in
batches/<timestamp>/ and its progress is stored in files there, so the app can
be closed and resumed at any step.
"""
import base64
import datetime
import glob
import json
import math
import os
import shutil

# The OCR model is already downloaded; don't contact HuggingFace on every start.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import cv2
import pandas as pd
import streamlit as st

import imageCropCV as cropper
from pipeline import render
from pipeline.anki import Anki
from pipeline.dictionary import lookup_many

ROOT = os.path.dirname(os.path.abspath(__file__))
BATCHES = os.path.join(ROOT, "batches")
CARDS_DIR = os.path.join(ROOT, cropper.OUT_DIR)
LAST_IMPORT = os.path.join(BATCHES, "last_import.txt")
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

st.set_page_config(page_title="Sheets → Anki", page_icon="🎴", layout="wide")


# -- small helpers -----------------------------------------------------------
def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def bpath(name):
    return os.path.join(st.session_state.batch, name)


def safe_name(word):
    return "".join("_" if c in '/\\:*?"<>|' else c for c in word)


@st.cache_data(show_spinner=False)
def thumb_uri(path, width=110):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    img = cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def image_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def new_batch():
    os.makedirs(BATCHES, exist_ok=True)
    path = os.path.join(BATCHES, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(os.path.join(path, "sheets"))
    os.makedirs(os.path.join(path, "crops"))
    os.makedirs(os.path.join(path, "images"))
    return path


def latest_open_batch():
    for b in sorted(glob.glob(os.path.join(BATCHES, "2*")), reverse=True):
        if os.path.exists(os.path.join(b, "rows.json")) and not os.path.exists(os.path.join(b, "result.json")):
            return b
    return None


def build_prompt(words):
    with open(os.path.join(ROOT, "prompt_template.txt"), encoding="utf-8") as f:
        template = f.read()
    n = len(words)
    cols = min(5, n)
    rows = math.ceil(n / cols)
    grid = f"{rows} row{'s' * (rows > 1)} × {cols} column{'s' * (cols > 1)}"
    return template.format(n=n, grid=grid,
                           words="\n".join(f"{i}. {w}" for i, w in enumerate(words, 1)))


@st.cache_data(ttl=20, show_spinner=False)
def anki_connected():
    # Cached: under WSL mirrored networking a closed port hangs until timeout
    # instead of refusing, so don't pay that on every rerun.
    return Anki(CFG).available()


# -- sidebar -------------------------------------------------------------------
anki = Anki(CFG)
with st.sidebar:
    st.header("🎴 Sheets → Anki")
    connected = anki_connected()
    if connected:
        st.success("AnkiConnect connected")
    else:
        st.warning("Anki not connected. Sending will fall back to an import file.")
    st.caption(f"Deck: **{CFG['deck']}** · Note type: **{CFG['notetype']}**")
    if st.button("Recheck connection"):
        anki_connected.clear()
        st.rerun()
    st.divider()
    if "batch" not in st.session_state:
        st.session_state.batch = latest_open_batch()
    if st.session_state.batch:
        st.caption(f"Current batch: `{os.path.basename(st.session_state.batch)}`")
    if st.button("Start a new batch"):
        st.session_state.batch = None
        st.rerun()

# -- step 0: make the next sheet ----------------------------------------------
with st.expander("✏️ Make the next sheet in ChatGPT (prompt generator)"):
    raw = st.text_area("Words for the next sheet (one per line, or separated by spaces/commas)", height=120)
    words = [w for w in raw.replace("、", " ").replace(",", " ").split() if w]
    if words:
        st.caption(f"{len(words)} words. Up to 10 per sheet works best.")
        st.code(build_prompt(words), language=None, wrap_lines=True)
        st.caption("Copy this (button at the top-right of the box), paste it into ChatGPT, "
                   "then download the image. It will show up in step 1 automatically.")

# -- step 1: sheets ----------------------------------------------------------------
st.header("1 · Card sheets")
if st.session_state.batch is None:
    src_downloads, src_upload, src_project = st.tabs(["From Downloads", "Upload", "Project folder"])
    chosen = []
    with src_downloads:
        try:
            with open(LAST_IMPORT) as f:
                since = float(f.read().strip())
        except (OSError, ValueError):
            since = (datetime.datetime.now() - datetime.timedelta(days=1)).timestamp()
        found = sorted(glob.glob(os.path.join(CFG["downloads_dir"], CFG["sheet_glob"])),
                       key=os.path.getmtime, reverse=True)[:40]
        if not found:
            st.info(f"No `{CFG['sheet_glob']}` files in Downloads.")
        for p in found:
            mt = os.path.getmtime(p)
            label = f"{os.path.basename(p)}  ·  {datetime.datetime.fromtimestamp(mt):%b %d %H:%M}"
            if st.checkbox(label, value=mt > since, key=f"dl::{p}"):
                chosen.append(("downloads", p))
    with src_upload:
        for up in st.file_uploader("Drop sheet images here", type=["png", "jpg", "jpeg", "webp"],
                                   accept_multiple_files=True) or []:
            chosen.append(("upload", up))
    with src_project:
        for p in sorted(glob.glob(os.path.join(ROOT, "*.png"))):
            if st.checkbox(os.path.basename(p), value=False, key=f"pj::{p}"):
                chosen.append(("project", p))

    if st.button(f"Crop & read {len(chosen)} sheet(s)", type="primary", disabled=not chosen):
        batch = new_batch()
        st.session_state.batch = batch
        rows = []
        progress = st.progress(0.0, text="Loading the OCR model…")
        for i, (kind, item) in enumerate(chosen):
            if kind == "upload":
                name = item.name
                dest = os.path.join(batch, "sheets", name)
                with open(dest, "wb") as f:
                    f.write(item.getbuffer())
            else:
                name = os.path.basename(item)
                dest = os.path.join(batch, "sheets", name)
                shutil.copy2(item, dest)  # copy only; the original stays where it was
            img = cv2.imread(dest)
            if img is None:
                st.error(f"Couldn't read {name}")
                continue
            for word, crop in cropper.crop_sheet(img):
                crop_path = os.path.join(batch, "crops", f"{len(rows):04d}.png")
                cv2.imwrite(crop_path, crop)
                rows.append({"crop": crop_path, "word": word, "sheet": name})
            progress.progress((i + 1) / len(chosen), text=f"Read {i + 1}/{len(chosen)} sheets")
        existing = anki.existing_words([r["word"] for r in rows if r["word"]])
        for r in rows:
            r["in_anki"] = r["word"] in existing
            r["include"] = bool(r["word"]) and not r["in_anki"]
        write_json(os.path.join(batch, "rows.json"), rows)
        picked = [os.path.getmtime(p) for kind, p in chosen if kind == "downloads"]
        if picked:
            with open(LAST_IMPORT, "w") as f:
                f.write(str(max(picked)))
        st.rerun()
    st.stop()

rows = read_json(bpath("rows.json"), [])
st.caption(f"{len(rows)} cards from {len({r['sheet'] for r in rows})} sheet(s).")

# -- step 2: review ----------------------------------------------------------------
st.header("2 · Review the words")
pending = read_json(bpath("pending.json"))
df = pd.DataFrame([{
    "card": thumb_uri(r["crop"]),
    "word": r["word"],
    "include": r["include"],
    "status": "Already in Anki" if r["in_anki"] else ("OCR failed: type the word" if not r["word"] else "New"),
    "sheet": r["sheet"],
} for r in rows])
st.caption("Fix any misread word by clicking it. Untick cards you don't want. "
           "Cards already in your deck start unticked.")
if pending is None and not any(r["include"] or not r["word"] for r in rows):
    st.info("Every card on these sheets is already in your deck. "
            "Fix a misread word below if needed, or click **Start a new batch** in the sidebar.")
edited = st.data_editor(
    df, hide_index=True, width="stretch", disabled=pending is not None,
    height=min(100 * len(df) + 40, 1040), row_height=100,
    column_config={
        "card": st.column_config.ImageColumn("Card", width="small"),
        "word": st.column_config.TextColumn("Word", required=True),
        "include": st.column_config.CheckboxColumn("Include"),
        "status": st.column_config.TextColumn("Status", disabled=True),
        "sheet": st.column_config.TextColumn("Sheet", disabled=True),
    },
)

if pending is None:
    if st.button("Look up words & prepare for Claude", type="primary"):
        picked = [(rows[i], w.strip()) for i, (w, inc) in enumerate(zip(edited["word"], edited["include"]))
                  if inc and str(w).strip()]
        words = [w for _, w in picked]
        dupes = sorted({w for w in words if words.count(w) > 1})
        already = anki.existing_words(words)
        if dupes:
            st.error(f"These words appear more than once: {', '.join(dupes)}. Untick the extras.")
        elif already:
            st.error(f"Already in your deck: {', '.join(sorted(already))}. Untick them.")
        elif not picked:
            st.error("No cards are ticked.")
        else:
            for i, (w, inc) in enumerate(zip(edited["word"], edited["include"])):
                rows[i]["word"], rows[i]["include"] = str(w).strip(), bool(inc)
            write_json(bpath("rows.json"), rows)
            os.makedirs(CARDS_DIR, exist_ok=True)
            for r, w in picked:
                fname = safe_name(w) + ".png"
                shutil.copyfile(r["crop"], bpath(os.path.join("images", fname)))
                shutil.copyfile(r["crop"], os.path.join(CARDS_DIR, fname))  # same as the CLI: overwrite by name
            with st.spinner("Looking up readings and kanji…"):
                drafts = lookup_many(words)
            write_json(bpath("pending.json"), {"batch": os.path.basename(st.session_state.batch), "words": drafts})
            st.rerun()
    st.stop()

# -- step 3: Claude ------------------------------------------------------------------
st.header("3 · Definitions & example sentences (Claude)")
content = read_json(bpath("content.json"))
if content is None:
    st.info(f"**{len(pending['words'])} words are ready.** In Claude Code (this project), type:")
    st.code("/sentences", language=None)
    st.caption("Claude reads only the word list (text), never the images. "
               "When it's done, click the button below.")
    if st.button("Load sentences", type="primary"):
        st.rerun()
    st.stop()

by_word = {c.get("word"): c for c in content.get("cards", [])}
missing = [d["word"] for d in pending["words"] if d["word"] not in by_word]
cards, problems = [], {}
for d in pending["words"]:
    c = by_word.get(d["word"])
    if c is None:
        continue
    fname = safe_name(d["word"]) + ".png"
    card = {**c, "image": fname if os.path.exists(bpath(os.path.join("images", fname))) else ""}
    cards.append(card)
    if render.validate(card):
        problems[d["word"]] = render.validate(card)
if missing:
    st.error(f"Claude's file is missing: {', '.join(missing)}. Run /sentences again after deleting content.json.")
if problems:
    for w, p in problems.items():
        st.error(f"{w}: {', '.join(p)}")
st.success(f"{len(cards)} cards ready.")

# -- step 4: preview & send ----------------------------------------------------------
st.header("4 · Preview & send to Anki")
for card in cards:
    with st.expander(f"{card['word']}  ·  {card['reading']}"):
        back = render.render_back(card)
        if card["image"]:
            back = back.replace(f'src="{card["image"]}"',
                                f'src="{image_uri(bpath(os.path.join("images", card["image"])))}" style="max-width:260px"')
        st.markdown(f"<div style='font-size:2em'>{render.render_front(card)}</div><hr>{back}",
                    unsafe_allow_html=True)

result = read_json(bpath("result.json"))
if result:
    st.success(f"Done: {result['added']} card(s) added to Anki.")
    if result.get("fallback_txt"):
        st.warning(f"{len(result['failed'])} card(s) went to the import file instead:\n\n"
                   f"`{result['fallback_txt_windows']}`\n\nIn Anki: File → Import → choose it "
                   "(duplicates: Update). Images were already copied into Anki's media folder.")
        for w, why in result["failed"]:
            st.caption(f"• {w}: {why}")
    st.stop()

if st.button(f"Send {len(cards)} card(s) to Anki", type="primary", disabled=bool(problems or missing)):
    images = {c["word"]: bpath(os.path.join("images", c["image"])) for c in cards if c["image"]}
    if anki.available():
        added, failed = anki.push(cards, images)
    else:
        added, failed = [], [(c, "Anki not connected") for c in cards]
    out = {"added": len(added), "failed": [(c["word"], why) for c, why in failed]}
    if failed:
        txt = bpath("deck.txt")
        anki.fallback([c for c, _ in failed], images, txt)
        out["fallback_txt"] = txt
        out["fallback_txt_windows"] = txt.replace("/mnt/c/", "C:\\").replace("/", "\\")
    write_json(bpath("result.json"), out)
    st.rerun()
