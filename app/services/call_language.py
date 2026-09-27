"""Which language a call was in, from the script the caller's words are written in.

Transcripts keep each language's own script (Telugu, Devanagari, Tamil…), so the caller's lines show the language
without another model call. A call with substantial Latin and Indic text is "mixed" (e.g. Telugu–English).
Romanized Hindi or Telugu written in Latin letters can't be told apart from English and counts as "en".
"""
from __future__ import annotations

import re
import unicodedata

# Unicode block → language code for the scripts callers use.
_SCRIPTS = (
    ((0x0C00, 0x0C7F), "te"),  # Telugu
    ((0x0900, 0x097F), "hi"),  # Devanagari (Hindi, Marathi…)
    ((0x0B80, 0x0BFF), "ta"),  # Tamil
    ((0x0C80, 0x0CFF), "kn"),  # Kannada
    ((0x0D00, 0x0D7F), "ml"),  # Malayalam
    ((0x0980, 0x09FF), "bn"),  # Bengali
    ((0x0A80, 0x0AFF), "gu"),  # Gujarati
    ((0x0A00, 0x0A7F), "pa"),  # Gurmukhi
    ((0x0600, 0x06FF), "ur"),  # Arabic script (Urdu)
)
NAMES = {"en": "English", "te": "Telugu", "hi": "Hindi", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam",
         "bn": "Bengali", "gu": "Gujarati", "pa": "Punjabi", "ur": "Urdu", "mixed": "Mixed (code-switching)",
         "unknown": "Unknown"}
MIXED_SHARE = 0.2
_SPEAKER = re.compile(r"^\[(USER|CALLER|ASSISTANT|AGENT)\]\s*", re.IGNORECASE)


def _caller_text(transcript: str) -> str:
    lines = (transcript or "").splitlines()
    marked = [ln for ln in lines if _SPEAKER.match(ln)]
    if not marked:
        return transcript or ""
    return "\n".join(_SPEAKER.sub("", ln) for ln in marked if ln.lstrip().upper().startswith(("[USER]", "[CALLER]")))


def _script(ch: str) -> str | None:
    code = ord(ch)
    for (low, high), lang in _SCRIPTS:
        if low <= code <= high:
            return lang
    if ch.isascii() and ch.isalpha():
        return "en"
    if unicodedata.category(ch).startswith("L") and code < 0x0250:  # accented Latin letters
        return "en"
    return None


def share(text: str | None, lang: str) -> float:
    """How much of the text's letters are in `lang`'s script (0 when there are no letters)."""
    counts: dict[str, int] = {}
    for ch in text or "":
        found = _script(ch)
        if found:
            counts[found] = counts.get(found, 0) + 1
    total = sum(counts.values())
    return counts.get(lang, 0) / total if total else 0.0


def detect(transcript: str | None) -> str:
    counts: dict[str, int] = {}
    for ch in _caller_text(transcript or ""):
        lang = _script(ch)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    total = sum(counts.values())
    if total < 3:
        return "unknown"
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    top, top_count = ranked[0]
    native = [lang for lang, n in counts.items() if lang != "en" and n / total >= MIXED_SHARE]
    if native and counts.get("en", 0) / total >= MIXED_SHARE:
        return "mixed"
    return top if top_count / total >= 0.5 else "mixed"
