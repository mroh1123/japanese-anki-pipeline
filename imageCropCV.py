import cv2
import numpy as np
import os
import glob
import re
import sys

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUT_DIR = "cards"
OCR_ENGINE = "manga-ocr"   # "manga-ocr" (robust, GPU, default) or "tesseract" (lightweight)

# ---------------------------------------------------------------------------
# OCR backends
# ---------------------------------------------------------------------------
_manga_reader = None


def ocr_tesseract(crop_bgr):
    import pytesseract
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    # psm 7 = treat the image as a single text line
    return pytesseract.image_to_string(
        rgb, lang="jpn", config="--psm 7"
    )


def ocr_manga(crop_bgr):
    global _manga_reader
    from manga_ocr import MangaOcr
    from PIL import Image
    if _manga_reader is None:
        _manga_reader = MangaOcr()
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    return _manga_reader(Image.fromarray(rgb))


def ocr_word(crop_bgr):
    """OCR one strip and return a cleaned Japanese-only word, or '' on failure."""
    raw = ocr_manga(crop_bgr) if OCR_ENGINE == "manga-ocr" else ocr_tesseract(crop_bgr)
    # Keep only Japanese script (kanji, hiragana, katakana, long-vowel mark);
    # drops stray spaces, latin letters, and OCR punctuation noise.
    return re.sub(r"[^一-鿿぀-ゟ゠-ヿー々]", "", raw)


def whiteness(crop_bgr):
    """Fraction of near-white pixels — the label band is mostly white, photos aren't."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    return float((gray > 230).mean())


# ---------------------------------------------------------------------------
# Card detection (same approach as before)
# ---------------------------------------------------------------------------
def find_cards(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)[1]
    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    boxes = [
        cv2.boundingRect(c)
        for c in contours
        if cv2.boundingRect(c)[2] > 200 and cv2.boundingRect(c)[3] > 300
    ]
    # Sort top-to-bottom then left-to-right
    return sorted(boxes, key=lambda b: (b[1] // 300, b[0]))


# A label band, as a fraction of card (y0, y1, x0, x1). Each position has a WIDE
# band (full enough for long multi-char words) and a TIGHT band used as a
# fallback: the tight band excludes the photo sliver and the surrounding empty
# white that make the OCR drop or hallucinate a lone-kanji label.
TOP_WIDE = (0.05, 0.27, 0.10, 0.90)
TOP_TIGHT = (0.04, 0.22, 0.18, 0.82)
BOTTOM_WIDE = (0.73, 0.95, 0.10, 0.90)
BOTTOM_TIGHT = (0.78, 0.96, 0.18, 0.82)

MAX_WORD_LEN = 8  # a card label is a few characters; longer = grabbed photo text


def band(card_bgr, b):
    h, w = card_bgr.shape[:2]
    y0, y1, x0, x1 = b
    return card_bgr[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def position_word(card_bgr, wide, tight):
    """Read one end of the card. Prefer the wide band; if it yields nothing or an
    implausibly long paragraph (text inside the photo), retry the tight crop.
    Whiteness comes from the wide band so it reflects how label-like the end is,
    for the top-vs-bottom tie-break."""
    sw = band(card_bgr, wide)
    white = whiteness(sw)
    word = ocr_word(sw)
    if not word or len(word) > MAX_WORD_LEN:
        retry = ocr_word(band(card_bgr, tight))
        if retry:
            return retry, white
    return word, white


def read_label(card_bgr):
    """The word may sit at the top OR bottom of a card. Read both ends and pick
    the better one: drop implausibly long reads, then trust the whiter (more
    label-like) end over incidental text inside the photo."""
    candidates = []
    for wide, tight in ((TOP_WIDE, TOP_TIGHT), (BOTTOM_WIDE, BOTTOM_TIGHT)):
        word, white = position_word(card_bgr, wide, tight)
        if word:
            candidates.append((white, word))

    if not candidates:
        return ""
    plausible = [c for c in candidates if len(c[1]) <= MAX_WORD_LEN]
    pool = plausible or candidates
    pool.sort(reverse=True)  # highest whiteness wins the tie-break
    return pool[0][1]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def crop_sheet(img):
    """Crop every card on a sheet (BGR image) and OCR its label.
    Returns [(word, crop_bgr)] in reading order; word is '' if OCR failed."""
    return [(read_label(img[y:y + h, x:x + w]), img[y:y + h, x:x + w])
            for (x, y, w, h) in find_cards(img)]


def process_image(path):
    img = cv2.imread(path)
    if img is None:
        print(f"  ! could not read {path}")
        return
    cards = crop_sheet(img)
    print(f"  found {len(cards)} cards")
    used = set()
    for i, (word, crop) in enumerate(cards, 1):
        if not word:
            word = f"card_{i:02d}"
            print(f"  card {i}: OCR failed -> '{word}'")
        else:
            print(f"  card {i}: {word}")
        # Avoid clobbering if two cards OCR to the same string
        name = word
        n = 2
        while name in used:
            name = f"{word}_{n}"
            n += 1
        used.add(name)
        cv2.imwrite(os.path.join(OUT_DIR, name + ".png"), crop)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # Use files passed on the command line, else auto-find every PNG in the
    # folder that isn't already a cropped card.
    args = sys.argv[1:]
    if args:
        images = args
    else:
        images = [
            p for p in glob.glob("*.png")
            if os.path.dirname(os.path.abspath(p)) != os.path.abspath(OUT_DIR)
        ]
    if not images:
        print("No input PNG images found.")
        return
    for path in images:
        print(f"Processing {path}")
        process_image(path)
    print("Done.")


if __name__ == "__main__":
    main()
