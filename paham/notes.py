"""
Uploaded lesson notes used as context.

Drop .md or .txt files into paham/lessons/. They are re-read automatically when they
change (no restart). The tutor calls search_lesson_notes, which returns only the most
relevant passages, so large notes don't inflate every model call.
"""

import re
from pathlib import Path

from .tools import normalize_text

LESSONS_DIR = Path(__file__).parent / "lessons"
SUPPORTED = {".md", ".txt"}
CHUNK_CHARS = 900

_cache: dict[str, object] = {"key": None, "chunks": []}


def lesson_files() -> list[Path]:
    if not LESSONS_DIR.exists():
        return []
    return sorted(p for p in LESSONS_DIR.iterdir() if p.suffix.lower() in SUPPORTED and p.name.lower() != "readme.md")


def _chunks() -> list[tuple[str, str]]:
    """(file name, passage) pairs, rebuilt only when a lesson file is added, changed or removed."""
    files = lesson_files()
    key = tuple((p.name, p.stat().st_mtime, p.stat().st_size) for p in files)
    if _cache["key"] != key:
        chunks = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            buf = ""
            for para in re.split(r"\n\s*\n", text):
                if buf and len(buf) + len(para) > CHUNK_CHARS:
                    chunks.append((path.name, buf.strip()))
                    buf = ""
                buf += para + "\n\n"
            if buf.strip():
                chunks.append((path.name, buf.strip()))
        _cache.update(key=key, chunks=chunks)
    return _cache["chunks"]  # type: ignore[return-value]


def search_lesson_notes(query: str) -> dict:
    """Searches the lesson notes uploaded by the teacher. Use them as the main source of facts and terms.

    Args:
        query: Topic or keywords in BM or English, e.g. 'pecahan setara', 'kadar tindak balas suhu'.
    """
    words = {w for w in re.findall(r"\w+", normalize_text(query)) if len(w) > 2}
    if not words:
        return {"status": "no_query"}
    scored = []
    for name, passage in _chunks():
        text = normalize_text(passage)
        score = sum(text.count(w) for w in words) + 3 * (normalize_text(query) in text)
        if score:
            scored.append((score, name, passage))
    if not scored:
        return {"status": "not_found", "files": [p.name for p in lesson_files()]}
    scored.sort(key=lambda s: -s[0])
    return {"status": "found", "passages": [{"file": n, "text": t} for _, n, t in scored[:3]]}
