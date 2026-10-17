"""
Deterministic tools for Paham.

Everything here is pure Python over small bundled JSON packs, so glossary lookups,
lesson cards, answer checking and arithmetic cost zero model tokens, work offline,
and never hallucinate. The LLM decides *when* to call them; code decides *what is true*.
"""

import ast
import difflib
import json
import math
import operator
import re
import unicodedata
from functools import lru_cache

from google.adk.tools.tool_context import ToolContext

from .config import DATA_DIR


# ------------------------------------------------------------------------------
# Data packs
# ------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_glossary() -> dict:
    """Loads the multilingual glossary pack."""
    return json.loads((DATA_DIR / "glossary.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_lessons() -> dict[str, dict]:
    """Loads lesson cards keyed by lesson id."""
    pack = json.loads((DATA_DIR / "lessons.json").read_text(encoding="utf-8"))
    return {lesson["id"]: lesson for lesson in pack["lessons"]}


@lru_cache(maxsize=1)
def practice_index() -> dict[str, tuple[dict, dict]]:
    """Maps practice question id -> (lesson, question)."""
    return {
        item["id"]: (lesson, item)
        for lesson in load_lessons().values()
        for item in lesson["practice"]
    }


# ------------------------------------------------------------------------------
# Localization helpers
# ------------------------------------------------------------------------------
LANGUAGE_ALIASES = {
    "en": ["english", "inggeris", "bahasa inggeris", "inggris"],
    "ms": ["malay", "bahasa melayu", "bahasa malaysia", "melayu", "bm"],
    "id": ["indonesian", "bahasa indonesia", "indonesia"],
    "zh": ["chinese", "mandarin", "中文", "华语", "華語", "汉语", "zh-cn", "zh-tw", "zh-hans", "zh-hant"],
    "ta": ["tamil", "தமிழ்"],
    "hi": ["hindi", "हिन्दी", "हिंदी"],
    "sw": ["swahili", "kiswahili"],
    "vi": ["vietnamese", "tiếng việt", "tieng viet"],
    "fil": ["filipino", "tagalog", "tl"],
    "es": ["spanish", "español", "espanol", "castellano"],
}
_LANGUAGE_LOOKUP = {alias: code for code, aliases in LANGUAGE_ALIASES.items() for alias in aliases}

# Languages whose students usually write decimals with a comma (2,5 = two and a half)
DECIMAL_COMMA_LANGUAGES = {"id", "vi", "es", "pt", "fr", "de", "it", "nl", "ru", "tr"}

COUNTRY_REGIONS = {
    "southeast_asia": ["malaysia", "indonesia", "philippines", "vietnam", "viet nam", "thailand", "singapore",
                       "brunei", "myanmar", "cambodia", "laos", "timor-leste", "east timor"],
    "south_asia": ["india", "pakistan", "bangladesh", "sri lanka", "nepal", "bhutan", "maldives", "afghanistan"],
    "africa": ["kenya", "tanzania", "uganda", "rwanda", "burundi", "ethiopia", "nigeria", "ghana", "south africa",
               "zambia", "zimbabwe", "malawi", "mozambique", "senegal", "cameroon", "democratic republic of the congo",
               "drc", "somalia", "sudan", "botswana", "namibia", "madagascar", "egypt", "morocco"],
    "latin_america": ["mexico", "méxico", "guatemala", "honduras", "el salvador", "nicaragua", "costa rica",
                      "panama", "colombia", "venezuela", "ecuador", "peru", "perú", "bolivia", "chile",
                      "argentina", "uruguay", "paraguay", "brazil", "brasil", "cuba", "dominican republic"],
}
_COUNTRY_LOOKUP = {country: region for region, countries in COUNTRY_REGIONS.items() for country in countries}
REGIONS = ("southeast_asia", "south_asia", "africa", "latin_america", "global")


def normalize_language(value: str) -> str:
    """Maps a language name or code ('Bahasa Melayu', 'ta', 'es-MX') to a short code."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return ""
    if cleaned in _LANGUAGE_LOOKUP:
        return _LANGUAGE_LOOKUP[cleaned]
    base = re.split(r"[-_]", cleaned)[0]
    if base in LANGUAGE_ALIASES or re.fullmatch(r"[a-z]{2,3}", base):
        return base
    return cleaned  # Unlisted language (e.g. 'iban'): keep it, the model can still use it


def language_name(code: str) -> str:
    """Human-readable language name for a code."""
    return load_glossary()["languages"].get(code, code)


def region_for(country: str) -> str:
    """Maps a country (or a region key) to one of the lesson-card regions."""
    cleaned = (country or "").strip().lower().replace(" ", "_")
    if cleaned in REGIONS:
        return cleaned
    return _COUNTRY_LOOKUP.get(cleaned.replace("_", " "), "global")


def normalize_digits(text: str) -> str:
    """Converts any Unicode decimal digits (Devanagari ४, Tamil ௪, Arabic-Indic ٤...) to ASCII."""
    out = []
    for ch in text:
        if not ch.isascii():
            digit = unicodedata.decimal(ch, None)
            if digit is not None:
                out.append(str(digit))
                continue
        out.append(ch)
    return "".join(out)


def normalize_text(text: str) -> str:
    """Casefolds and strips Latin accents (nổi -> noi) while leaving Indic/CJK scripts intact."""
    decomposed = unicodedata.normalize("NFKD", normalize_digits(text).casefold())
    out = []
    prev_latin = False
    for ch in decomposed:
        if unicodedata.combining(ch) and prev_latin:
            continue  # Drop accents on Latin letters only; Tamil/Hindi vowel signs are combining too
        out.append(ch)
        prev_latin = ch < "ɐ"
    return unicodedata.normalize("NFC", "".join(out)).strip()


# ------------------------------------------------------------------------------
# Learner profile (persisted with the 'user:' prefix so it survives new sessions)
# ------------------------------------------------------------------------------
def get_profile(state) -> dict:
    """Reads the learner profile from session state."""
    return {
        "language": state.get("user:language", ""),
        "grade_level": state.get("user:grade_level", ""),
        "country": state.get("user:country", ""),
        "region": state.get("user:region", "southeast_asia"),  # Malaysian learners by default
        "data_saver": bool(state.get("user:data_saver", False)),
    }


def bandwidth_mode(state) -> str:
    """Returns 'sms', 'data_saver' or 'standard' for the current request."""
    if state.get("channel") == "sms":
        return "sms"
    if state.get("user:data_saver"):
        return "data_saver"
    return "standard"


def set_learner_profile(
    tool_context: ToolContext,
    language: str = "",
    grade_level: str = "",
    country: str = "",
    data_saver: str = "",
) -> dict:
    """Saves the learner's preferences so every later reply is tailored to them.

    Call this as soon as you learn, or can confidently infer, any of these fields.
    Leave a field empty to keep its current value.

    Args:
        language: Preferred language as a code or name, e.g. 'ms', 'Tamil', 'sw', 'es'.
        grade_level: School year or age, e.g. 'Form 2', 'Grade 7', '13 years old'.
        country: Country where the learner lives, e.g. 'Malaysia', 'Kenya', 'Peru'.
        data_saver: 'on' for very short replies (slow or expensive internet), 'off' for normal replies.
    """
    state = tool_context.state
    if language:
        state["user:language"] = normalize_language(language)
    if grade_level:
        state["user:grade_level"] = grade_level.strip()[:40]
    if country:
        state["user:country"] = country.strip()[:40]
        state["user:region"] = region_for(country)
    if data_saver:
        state["user:data_saver"] = data_saver.strip().lower() in ("on", "true", "yes", "1")
    return {"status": "saved", "profile": get_profile(state)}


# ------------------------------------------------------------------------------
# Glossary
# ------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _term_index() -> dict[str, str]:
    """Maps every normalized English key and translation back to its English key."""
    index = {}
    for key, entry in load_glossary()["terms"].items():
        index[normalize_text(key)] = key
        for lang in load_glossary()["languages"]:
            if lang in entry:
                index.setdefault(normalize_text(entry[lang]), key)
    return index


def find_term(term: str) -> str | None:
    """Finds the glossary key for a term written in English or any supported language."""
    index = _term_index()
    needle = normalize_text(term)
    if needle in index:
        return index[needle]
    for suffix, replacement in (("ies", "y"), ("es", ""), ("s", "")):
        if needle.endswith(suffix) and needle[: -len(suffix)] + replacement in index:
            return index[needle[: -len(suffix)] + replacement]
    close = difflib.get_close_matches(needle, index.keys(), n=1, cutoff=0.8)
    return index[close[0]] if close else None


def lookup_stem_term(term: str, tool_context: ToolContext, language: str = "") -> dict:
    """Looks up the standard classroom term for a STEM word in the learner's language.

    Use it whenever you introduce a technical term, so you use the official school
    term instead of inventing a translation. Works in reverse too ('ketumpatan' -> density).

    Args:
        term: The word in English or any supported language, e.g. 'density', 'pecahan', '光合作用'.
        language: Target language code. Defaults to the learner's profile language.
    """
    key = find_term(term)
    if key is None:
        suggestions = difflib.get_close_matches(term.lower(), load_glossary()["terms"].keys(), n=3, cutoff=0.5)
        return {
            "status": "not_found",
            "suggestions": suggestions,
            "note": "Not in the offline glossary. Translate carefully and keep the English term in brackets.",
        }
    entry = load_glossary()["terms"][key]
    target = normalize_language(language) or tool_context.state.get("user:language", "")
    result = {
        "status": "found",
        "english": key,
        "subject": entry["subject"],
        "definition_en": entry["definition"],
    }
    if target and target != "en":
        result["language"] = target
        result["local_term"] = entry.get(target)
        if result["local_term"] is None:
            result["note"] = f"No glossary entry for '{target}'. Translate carefully and keep the English term in brackets."
    return result


# ------------------------------------------------------------------------------
# Lesson cards
# ------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _topic_index() -> dict[str, str]:
    index = {}
    for lesson_id, lesson in load_lessons().items():
        for name in [lesson_id, lesson_id.replace("_", " "), lesson["title"], *lesson.get("aliases", [])]:
            index.setdefault(normalize_text(name), lesson_id)
    return index


def resolve_topic(topic: str) -> str | None:
    """Matches free text ('Ohm's law', 'pecahan', 'float or sink') to a lesson id."""
    index = _topic_index()
    needle = normalize_text(topic)
    if needle in index:
        return index[needle]
    for name, lesson_id in index.items():
        if (len(name) >= 4 and name in needle) or (len(needle) >= 4 and needle in name):
            return lesson_id
    close = difflib.get_close_matches(needle, index.keys(), n=1, cutoff=0.7)
    return index[close[0]] if close else None


def list_topics(subject: str = "") -> dict:
    """Lists the offline lesson topics (id, title, subject, level).

    Args:
        subject: Optional filter: 'math', 'physics', 'chemistry', 'biology' or 'computing'.
    """
    wanted = subject.strip().lower()
    topics = [
        {"id": lesson["id"], "title": lesson["title"], "subject": lesson["subject"], "level": lesson["level"]}
        for lesson in load_lessons().values()
        if not wanted or lesson["subject"] == wanted
    ]
    return {"topics": topics}


def get_lesson_card(topic: str, tool_context: ToolContext) -> dict:
    """Fetches a short, teacher-checked lesson card with an everyday example from the learner's region.

    The card is written in simple English. Explain it in the learner's language and
    adapt it; do not paste it word for word.

    Args:
        topic: Topic id or free text, e.g. 'fractions', "Ohm's law", 'photosynthesis'.
    """
    lesson_id = resolve_topic(topic)
    if lesson_id is None:
        return {"status": "not_found", "available": [t["id"] for t in list_topics()["topics"]]}
    lesson = load_lessons()[lesson_id]
    profile = get_profile(tool_context.state)
    region = profile["region"] or "southeast_asia"
    language = profile["language"]
    terms = load_glossary()["terms"]
    return {
        "status": "found",
        "id": lesson_id,
        "title": lesson["title"],
        "level": lesson["level"],
        "key_idea": lesson["key_idea"],
        "formula": lesson.get("formula", ""),
        "worked_example": lesson["worked_example"],
        "common_mistake": lesson["misconception"],
        "local_example": lesson["examples"].get(region, lesson["examples"]["global"]),
        "key_terms": {
            term: terms[term].get(language, term) if language and language != "en" else term
            for term in lesson.get("terms", [])
        },
        "practice_questions_available": len(lesson["practice"]),
    }


# ------------------------------------------------------------------------------
# Practice and progress
# ------------------------------------------------------------------------------
# A number never starts right after a letter or '^': the 3 in 'cm3', 2 in 'm/s2' or 'm^2' is a unit
_NOT_UNIT = r"(?<![^\W\d_])(?<!\^)"
_NUMBER_PATTERN = re.compile(
    _NOT_UNIT + r"(?P<whole>-?\d+)\s+(?P<mixed_num>\d+)\s*/\s*(?P<mixed_den>\d+)"   # mixed number: 1 1/2
    r"|" + _NOT_UNIT + r"(?P<num>-?\d+(?:[.,]\d+)*)\s*/\s*(?P<den>\d+(?:[.,]\d+)*)"  # fraction: 3/4
    r"|" + _NOT_UNIT + r"(?P<value>-?\d+(?:[.,]\d+)*)(?P<pct>\s*%)?"                 # number, optional %
)


def _to_float(token: str, language: str) -> float:
    """Interprets '.' and ',' as decimal or thousands separators, depending on the learner's language."""
    if "." in token and "," in token:
        decimal = "." if token.rfind(".") > token.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        return float(token.replace(thousands, "").replace(decimal, "."))
    for sep in (",", "."):
        if sep in token:
            parts = token.split(sep)
            uses_comma = language in DECIMAL_COMMA_LANGUAGES
            looks_like_thousands = len(parts) > 2 or (
                len(parts[1]) == 3
                and parts[0].lstrip("-") not in ("", "0")
                and ((sep == ",") != uses_comma)
            )
            return float(token.replace(sep, "") if looks_like_thousands else token.replace(sep, "."))
    return float(token)


def parse_number(text: str, language: str = "") -> tuple[float, bool] | None:
    """Extracts the learner's final numeric answer.

    Handles '3/4', '1 1/2', '0,75' (decimal comma), '1,500', '45%', Devanagari or Tamil
    digits, and trailing units ('12 km/h'). Returns (value, was_percent) or None.
    """
    cleaned = normalize_digits(text).replace("−", "-").replace("⁄", "/")
    matches = list(_NUMBER_PATTERN.finditer(cleaned))
    if not matches:
        return None
    m = matches[-1]  # The answer is usually the last number written ('x = 5')
    try:
        if m.group("whole") is not None:
            whole = float(m.group("whole"))
            frac = float(m.group("mixed_num")) / float(m.group("mixed_den"))
            return (whole - frac if whole < 0 else whole + frac), False
        if m.group("num") is not None:
            return _to_float(m.group("num"), language) / _to_float(m.group("den"), language), False
        return _to_float(m.group("value"), language), bool(m.group("pct"))
    except (ValueError, ZeroDivisionError):
        return None


def grade_answer(item: dict, student_answer: str, language: str = "") -> bool | None:
    """Grades an answer against a practice item. Returns None if the answer is unreadable."""
    kind = item.get("type", "number")
    if kind == "number":
        parsed = parse_number(student_answer, language)
        if parsed is None:
            return None
        value, was_percent = parsed
        candidates = [value, value / 100] if was_percent else [value]
        rel_tol = item.get("tolerance", 0.015)
        return any(math.isclose(c, item["answer"], rel_tol=rel_tol, abs_tol=1e-9) for c in candidates)

    answer = normalize_text(student_answer)
    if not answer:
        return None
    if kind == "exact":
        tokens = set(re.findall(r"\w+", answer))
        return any(normalize_text(a) in tokens for a in item["accepts"])
    # Free text: any accepted word present, and no word that signals the opposite answer
    if any(normalize_text(r) in answer for r in item.get("rejects", [])):
        return False
    return any(normalize_text(a) in answer for a in item["accepts"])


def _progress(state) -> dict:
    return dict(state.get("user:progress", {}))


def get_practice_question(topic: str, tool_context: ToolContext) -> dict:
    """Gets the learner's next unsolved practice question for a topic.

    The answer is hidden from you on purpose: grade the learner's reply with check_answer.
    Translate the question into the learner's language and adapt names/places to their region.

    Args:
        topic: Topic id or free text, e.g. 'percentages', 'binary'.
    """
    lesson_id = resolve_topic(topic)
    if lesson_id is None:
        return {"status": "not_found", "available": [t["id"] for t in list_topics()["topics"]]}
    lesson = load_lessons()[lesson_id]
    solved = set(_progress(tool_context.state).get(lesson_id, {}).get("solved", []))
    for item in lesson["practice"]:
        if item["id"] not in solved:
            return {
                "status": "ok",
                "question_id": item["id"],
                "question": item["question"],
                "answer_format": "a number" if item.get("type", "number") == "number" else "a word or short phrase",
                "remaining_in_topic": sum(1 for p in lesson["practice"] if p["id"] not in solved),
            }
    return {"status": "topic_complete", "suggested_next": _suggest_next(tool_context.state, lesson["subject"])}


def check_answer(question_id: str, student_answer: str, tool_context: ToolContext) -> dict:
    """Checks the learner's answer to a practice question in code (never guess correctness yourself).

    Pass the learner's reply exactly as they wrote it; any language, digits, fraction or
    decimal-comma format is fine. First wrong try returns a hint; the second returns the solution.

    Args:
        question_id: The question_id returned by get_practice_question.
        student_answer: The learner's answer, exactly as written.
    """
    found = practice_index().get(question_id.strip())
    if found is None:
        return {"status": "unknown_question", "note": "Call get_practice_question first."}
    lesson, item = found
    state = tool_context.state
    result = grade_answer(item, student_answer, state.get("user:language", ""))
    if result is None:
        return {"status": "unreadable", "note": f"Ask the learner to reply with just {'a number' if item.get('type', 'number') == 'number' else 'a short answer'}."}

    attempts = dict(state.get("attempts", {}))
    attempts[question_id] = attempts.get(question_id, 0) + 1
    state["attempts"] = attempts

    progress = _progress(state)
    topic = dict(progress.get(lesson["id"], {"attempted": 0, "correct": 0, "solved": []}))
    topic["attempted"] += 1
    if result:
        topic["correct"] += 1
        if question_id not in topic["solved"]:
            topic["solved"] = [*topic["solved"], question_id]
    progress[lesson["id"]] = topic
    state["user:progress"] = progress

    if result:
        return {"correct": True, "solution": item["solution"], "topic_mastery": _mastery_label(topic, lesson)}
    if attempts[question_id] < 2:
        return {"correct": False, "attempt": 1, "hint": item["hint"],
                "note": "Encourage them, give the hint in their language, and let them try again. Do not reveal the answer."}
    return {"correct": False, "attempt": attempts[question_id], "solution": item["solution"],
            "note": "Walk through the solution step by step, then offer another question."}


def _mastery_label(topic: dict, lesson: dict) -> str:
    if not topic.get("attempted"):
        return "not started"
    accuracy = topic["correct"] / topic["attempted"]
    if len(topic.get("solved", [])) == len(lesson["practice"]) and accuracy >= 0.6:
        return "mastered"
    return "getting there" if accuracy >= 0.5 else "keep practising"


def _suggest_next(state, subject: str = "") -> str:
    """Suggests the next topic: weakest started topic first, else an unstarted one (same subject preferred)."""
    progress = _progress(state)
    lessons = load_lessons()
    weak = [
        (stats["correct"] / stats["attempted"], lesson_id)
        for lesson_id, stats in progress.items()
        if lesson_id in lessons and stats.get("attempted")
        and _mastery_label(stats, lessons[lesson_id]) != "mastered"
    ]
    if weak:
        return min(weak)[1]
    unstarted = [lid for lid in lessons if lid not in progress]
    same_subject = [lid for lid in unstarted if lessons[lid]["subject"] == subject]
    return (same_subject or unstarted or list(lessons))[0]


def get_progress_report(tool_context: ToolContext) -> dict:
    """Summarises the learner's practice history across all sessions and suggests what to study next."""
    progress = _progress(tool_context.state)
    lessons = load_lessons()
    topics = [
        {
            "topic": lessons[lesson_id]["title"],
            "correct": stats["correct"],
            "attempted": stats["attempted"],
            "solved": f"{len(stats.get('solved', []))}/{len(lessons[lesson_id]['practice'])}",
            "status": _mastery_label(stats, lessons[lesson_id]),
        }
        for lesson_id, stats in progress.items()
        if lesson_id in lessons
    ]
    return {"topics": topics, "suggested_next_topic": _suggest_next(tool_context.state)}


# ------------------------------------------------------------------------------
# Safe calculator (models are bad at arithmetic; this is exact)
# ------------------------------------------------------------------------------
_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Pow: operator.pow, ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    "sqrt": math.sqrt, "abs": abs, "round": round,
    "sin": lambda d: math.sin(math.radians(d)),   # degrees, as in school
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
    "log": math.log10, "ln": math.log, "exp": math.exp,
}
_CONSTANTS = {"pi": math.pi, "e": math.e, "g": 9.8}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e6):
            raise ValueError("number too large")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS
            and not node.keywords and 1 <= len(node.args) <= 2):
        return _FUNCTIONS[node.func.id](*[_eval_node(arg) for arg in node.args])
    raise ValueError("unsupported expression")


def calculate(expression: str) -> dict:
    """Evaluates an arithmetic expression exactly. Use it for every calculation you show the learner.

    Supports + - * / ** ( ), x% (percent), sqrt, abs, round, sin/cos/tan (in DEGREES),
    log (base 10), ln, exp, and the constants pi, e and g (9.8 m/s²).

    Args:
        expression: For example '0.15 * 200', '(20 - 0) / 5', 'sqrt(3**2 + 4**2)', '25% * 80'.
    """
    if len(expression) > 200:
        return {"status": "error", "error": "expression too long"}
    cleaned = (
        normalize_digits(expression)
        .replace("×", "*").replace("÷", "/").replace("^", "**").replace("−", "-")
        .replace("√", "sqrt").replace("π", "pi")
    )
    cleaned = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", cleaned)
    try:
        value = _eval_node(ast.parse(cleaned, mode="eval"))
    except ZeroDivisionError:
        return {"status": "error", "error": "division by zero"}
    except (SyntaxError, ValueError, TypeError, OverflowError) as exc:
        return {"status": "error", "error": str(exc) or "invalid expression"}
    if isinstance(value, float):
        value = int(value) if value.is_integer() and abs(value) < 1e15 else float(f"{value:.10g}")
    return {"status": "ok", "expression": expression, "result": value}


TUTOR_TOOLS = [
    set_learner_profile,
    lookup_stem_term,
    list_topics,
    get_lesson_card,
    get_practice_question,
    check_answer,
    get_progress_report,
    calculate,
]
