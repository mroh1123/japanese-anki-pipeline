---
description: Write definitions + example sentences for the pending flashcard batch
---

Fill in the Claude part of the newest flashcard batch. This is a text-only task:
do NOT open any images, do NOT read the Anki collection, do NOT invoke the
japanese-anki-cards skill (its documented format is not the one this deck uses).

1. Find the newest `batches/*/pending.json` in this project that has no
   `content.json` beside it. If there is none, say so and stop.
2. Read it. Each entry has `word`, a dictionary-drafted `reading`, English
   `glosses_en` (reference only), and `kanji` drafts with on/kun readings and
   English `meanings_en` (reference only).
3. Write `content.json` in the same folder (UTF-8, pretty JSON) with exactly:

```json
{"cards": [
  {"word": "...", "reading": "...", "definition": "...", "example": "...",
   "kanji": [{"char": "...", "on": ["..."], "kun": ["..."], "gloss": "..."}],
   "en_hint": ""}
]}
```

One card per pending word, same order, same `word` (never change it).

## Field rules (match the user's existing deck exactly)

- **reading**: hiragana. Keep the draft unless it's wrong for this word (e.g. 街→まち, 床→ゆか).
- **definition**: a short monolingual Japanese dictionary-style definition ending in 。.
  Can add a second short phrase or an antonym with ⇔. No English.
  **Keep it short: about 12–20 characters** (the deck's median is 16).
- **example**: one fresh, natural Japanese sentence using the word, not much harder
  than the word itself, with a 、 where it reads naturally. Ends in 。. No English.
  **Keep it short and everyday: about 12–20 characters** (median 16), e.g.
  `この道は、幅が狭い。` rather than a long sentence with extra clauses.
- **kanji**: every kanji in the word, in order (no entries for kana). Start from the
  draft on/kun lists and keep only the salient readings, typically 1–2 of each, and
  include the one actually used in this word. On'yomi in katakana; kun'yomi in hiragana
  with okurigana in parentheses: `よ(ぶ)`. Omit `on` or `kun` (empty list) if
  irrelevant. **gloss** is short Japanese: usually the kun-reading word and/or a
  1–2 word meaning joined by ・ (e.g. `よぶ`, `こたえる・応じる`, `おきて・決まり（国字）`).
- **kanji_custom** (instead of `kanji`, rarely): for ateji/jukujikun where a per-kanji
  breakdown would mislead, give a raw HTML string like the 旦那 example below.
- **en_hint**: usually "". Add a terse English gloss only for abstract or literary
  words (e.g. 呼応, 悄然, 反芻, 天啓): `acting in concert; responding`.
- Never put a tab, newline, or `<`/`>` (except in kanji_custom) in any field.

## Real examples from the deck

```json
{"word": "後悔", "reading": "こうかい",
 "definition": "あとになって、しなければよかったと悔やむこと。",
 "example": "言いすぎたことを、後悔している。",
 "kanji": [{"char": "後", "on": ["ゴ", "コウ"], "kun": ["のち", "あと", "うし(ろ)"], "gloss": "あと・のち"},
           {"char": "悔", "on": ["カイ"], "kun": ["く(いる)", "く(やむ)"], "gloss": "くやむ"}],
 "en_hint": ""}
{"word": "呼応", "reading": "こおう",
 "definition": "互いに呼びかけ合い、調子を合わせること。",
 "example": "各地のデモが、呼応して広がった。",
 "kanji": [{"char": "呼", "on": ["コ"], "kun": ["よ(ぶ)"], "gloss": "よぶ"},
           {"char": "応", "on": ["オウ"], "kun": ["こた(える)"], "gloss": "こたえる・応じる"}],
 "en_hint": "acting in concert; responding"}
{"word": "掟", "reading": "おきて",
 "definition": "仲間内で守るべき、決まり。",
 "example": "ムラの掟に背いた者は、追放される。",
 "kanji": [{"char": "掟", "on": [], "kun": ["おきて"], "gloss": "おきて・決まり（国字）"}],
 "en_hint": ""}
{"word": "旦那", "reading": "だんな",
 "definition": "妻から見た夫。また、商家などの主人。",
 "example": "それぞれの旦那と子供を連れてきた。",
 "kanji_custom": "<b>旦</b>＝あさ ／ <b>那</b>＝（疑問の語）<br>※ 当て字。サンスクリット語の「ダーナ（＝布施・施し）」を仏教を通して音で写したもの。「施す人」→「主人・夫」と意味が移った。漢字は音を借りただけ。",
 "en_hint": ""}
```

4. Reply with just: how many cards you wrote, and any readings you changed or
   words you were unsure about. Then tell the user to click **Load sentences** in the app.
