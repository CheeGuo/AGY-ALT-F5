"""
System instruction for Paham (Cikgu PAHAM).

The teaching behaviour lives in master_prompt.md (edit that file to change how Cikgu
PAHAM teaches). This module appends a short app-specific section, rebuilt every turn:
learner profile, uploaded lesson notes, available tools, display format and length limits.
"""

from pathlib import Path

from .notes import lesson_files
from .tools import bandwidth_mode, get_profile, language_name

MASTER_PROMPT = (Path(__file__).parent / "master_prompt.md").read_text(encoding="utf-8")

APP_CONTEXT = """

## 17. App Context (Paham app; overrides earlier sections where they conflict)

**Learner profile:** {learner}

**Language:** {language_rule}

**Facts and sources:**
- {notes_rule}
- Use the `calculate` tool for any arithmetic you show; never guess numbers.
- Use `lookup_stem_term` for official BM school terms and their English equivalents.
- For practice, you may use `get_practice_question`, and grade answers ONLY with `check_answer`.
- When you learn the student's age, school year or country, save it with `set_learner_profile`.

**Display format:** this app shows plain text only. LaTeX is NOT supported: write formulas as plain text (v = s / t, x^2, 3/4, sqrt(9)). Markdown tables and bold are not rendered; use short paragraphs and numbered steps. Code is shown as plain text, so keep code short and correctly indented.

**Length:** {length_rule}"""

LENGTH_RULES = {
    "standard": "Phase 1 about 50-120 words; Phase 2 and direct answers under about 200 words unless the student asks for more.",
    "data_saver": "DATA SAVER is on: keep every reply under about 70 words.",
    "sms": "SMS channel (paid per message): at most 3 short sentences, under 45 words, one paragraph.",
}


def build_instruction(state) -> str:
    """Master prompt + app context for the current learner and channel."""
    profile = get_profile(state)
    parts = []
    if profile["grade_level"]:
        parts.append(f"school year/age = {profile['grade_level']}")
    if profile["country"]:
        parts.append(f"country = {profile['country']}")
    learner = "; ".join(parts) if parts else "not known yet (infer tentatively; ask only if it materially changes the lesson)"

    if profile["language"] and profile["language"] != "ms":
        language_rule = f"The student chose {language_name(profile['language'])}: reply in that language, keeping the same persona and method."
    else:
        language_rule = "Reply in Bahasa Melayu Malaysia by default, even if the student writes in English. Switch only if the student clearly asks."

    files = [p.name for p in lesson_files()]
    if files:
        notes_rule = (f"The teacher uploaded lesson notes ({', '.join(files[:20])}). Call `search_lesson_notes` first for related "
                      "questions and prefer their facts, terms and examples over your own.")
    else:
        notes_rule = "No lesson notes uploaded yet; use the Malaysian national syllabus and `get_lesson_card` when relevant."

    return MASTER_PROMPT + APP_CONTEXT.format(
        learner=learner,
        language_rule=language_rule,
        notes_rule=notes_rule,
        length_rule=LENGTH_RULES[bandwidth_mode(state)],
    )
