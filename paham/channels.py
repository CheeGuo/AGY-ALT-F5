"""
Output shaping for low-capability channels (feature-phone SMS, read-aloud, tiny screens).

SMS cost is per segment: a GSM-7 message fits 160 chars (153 per part when split), but
a single non-GSM character (Tamil, Hindi, Chinese, most emoji, Vietnamese accents) forces
UCS-2, which fits only 70 (67 per part). We count segments exactly and page long replies,
so a learner on a basic phone never receives a surprise 10-part message.
"""

import re

# GSM 03.38 basic character set (+ extension table chars, which cost 2 septets)
_GSM_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_EXTENDED = set("^{}\\[~]|€")

# Words a learner can text to get the next page of a long reply, in several languages
MORE_KEYWORDS = {"more", "next", "lagi", "seterusnya", "lanjut", "zaidi", "endelea", "tiếp", "tiep",
                 "más", "mas", "sige", "पुढे", "आगे", "மேலும்", "更多", "继续", "m"}


def to_plain_text(text: str) -> str:
    """Strips Markdown so replies read cleanly on basic screens and in text-to-speech."""
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)                    # code fences
    text = re.sub(r"`([^`]*)`", r"\1", text)                        # inline code
    text = re.sub(r"\*\*([^*]+)\*\*|__([^_]+)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"\1", text)  # *italic*
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)       # headings
    text = re.sub(r"^\s*[-*•]\s+", "- ", text, flags=re.M)          # bullets
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)            # links
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_gsm7(text: str) -> bool:
    """True if the text can be sent with the cheap GSM-7 encoding."""
    return all(ch in _GSM_BASIC or ch in _GSM_EXTENDED for ch in text)


def sms_length(text: str) -> int:
    """Length in encoding units (septets for GSM-7, UTF-16 code units for UCS-2)."""
    if is_gsm7(text):
        return sum(2 if ch in _GSM_EXTENDED else 1 for ch in text)
    return len(text.encode("utf-16-le")) // 2


def sms_segments(text: str) -> int:
    """Number of SMS segments the text will be billed as."""
    single, multi = (160, 153) if is_gsm7(text) else (70, 67)
    length = sms_length(text)
    return 1 if length <= single else -(-length // multi)


_GSM_FRIENDLY = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...",
    "×": "x", "÷": "/", "−": "-", "²": "^2", "³": "^3", "°": " deg", " ": " ",
})


def sms_friendly(text: str) -> str:
    """Plain text with typographic characters swapped for GSM-7 ones where that keeps meaning.

    One curly quote would otherwise flip a whole English or Malay reply into UCS-2
    and more than double its cost.
    """
    text = to_plain_text(text).translate(_GSM_FRIENDLY)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n+", "\n", text)).strip()


def paginate_sms(text: str, max_segments: int) -> list[str]:
    """Splits text into pages that each fit in `max_segments` SMS segments.

    Breaks at sentence or word boundaries. Every page except the last ends with a
    '(MORE)' marker telling the learner how to fetch the next page.
    """
    text = sms_friendly(text)
    marker = " (MORE)"
    single, multi = (160, 153) if is_gsm7(text) else (70, 67)
    budget = single if max_segments == 1 else multi * max_segments

    pages = []
    remaining = text
    while sms_length(remaining) > budget:
        limit = budget - sms_length(marker)
        cut = _cut_point(remaining, limit)
        pages.append(remaining[:cut].rstrip() + marker)
        remaining = remaining[cut:].lstrip()
    pages.append(remaining)
    return pages


def _cut_point(text: str, limit: int) -> int:
    """Largest index <= limit (in SMS units) that ends at a sentence, else a word boundary."""
    end = 0
    used = 0
    for i, ch in enumerate(text):
        used += sms_length(ch)
        if used > limit:
            break
        end = i + 1
    window = text[:end]
    for pattern in (r"[.!?。！？]\s", r"\s"):
        hits = [m.end() for m in re.finditer(pattern, window)]
        if hits and hits[-1] > end // 2:
            return hits[-1]
    return end
