# Sheets → Anki

A local web app that turns AI-generated Japanese vocabulary card sheets into Anki flashcards,
using the cheapest tool for each step:

| Step | Done by | Cost |
|---|---|---|
| Card sheets (a grid of illustrated cards, one word each) | ChatGPT; the app writes the prompt | your ChatGPT plan |
| Find each card and read its word | OpenCV + [manga-ocr](https://github.com/kha-white/manga-ocr), on your GPU | free |
| Reading + per-kanji on/kun readings | Offline JMdict / KANJIDIC2 via [jamdict](https://github.com/neocl/jamdict) | free |
| Japanese definition + example sentence | Claude Code `/sentences` command, text only | small |
| Add to Anki | [AnkiConnect](https://ankiweb.net/shared/info/2055492159), or a `.txt` import file as fallback | free |

The app runs only on your own machine (`127.0.0.1`); nothing is hosted online.

## Workflow

1. **Prompt generator:** paste the next words; copy the generated prompt into ChatGPT and download the sheet.
2. **Card sheets:** new `ChatGPT Image*.png` files in Downloads are picked up automatically (copied, never moved).
3. **Review:** each crop is shown next to its OCR'd word; fix misreads, untick cards you don't want.
   Words already in your deck are flagged and skipped.
4. **Claude:** run `/sentences` in Claude Code in this folder; it writes `content.json` for the batch.
5. **Preview & send:** cards are rendered exactly like the existing deck and pushed via AnkiConnect.
   If Anki isn't reachable, a `deck.txt` import file is written and the images are copied into Anki's media folder.

Each run lives in `batches/<timestamp>/`, so you can close the app and resume later.

## Setup (Windows + WSL)

```bash
python3 -m venv venv
venv/bin/pip install opencv-python numpy pillow manga-ocr streamlit jamdict jamdict-data requests
```

- In Anki, install AnkiConnect (code `2055492159`) and set its `webBindPort` to match
  `ankiconnect_url` in `config.json` (default `8766`).
- Edit `config.json` for your deck name, note type, Anki profile folder and Downloads folder.
- Start the app with `start_app.bat`, or `venv/bin/streamlit run app.py`; it opens at http://localhost:8501.

## Files

- `app.py`: the Streamlit app
- `imageCropCV.py`: card detection + OCR (also usable on its own: `venv/bin/python imageCropCV.py`)
- `pipeline/render.py`: card HTML in the deck's exact format, plus the `.txt` import writer
- `pipeline/dictionary.py`: offline dictionary drafts
- `pipeline/anki.py`: AnkiConnect client, duplicate check, fallback
- `.claude/commands/sentences.md`: the `/sentences` instructions for Claude Code
- `prompt_template.txt`: the ChatGPT sheet prompt (editable)
