"""
Paham: Localized & Inclusive STEM Learning Agent (Google ADK)

Architecture:
- One Flash-Lite LlmAgent (cheapest multimodal tier: reads typed text, photos of
  homework and voice notes in any language). No sub-agent hops: each extra model
  call costs latency that students on 2G/3G feel.
- Deterministic Python tools for everything that must be correct: curriculum
  glossary, lesson cards, answer grading, progress and arithmetic (zero tokens).
- Dynamic instruction built from the learner profile (language, school year,
  country/region) stored with the 'user:' prefix, so it persists across sessions.
- before_model_callback enforces a bandwidth budget: caps output tokens per mode
  (standard / data saver / SMS), trims old turns, and stops re-sending old photos.
- after_model_callback makes sure a capped reply still ends on a full sentence.
"""

import re

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .config import CONFIG
from .notes import search_lesson_notes
from .prompts import build_instruction
from .tools import TUTOR_TOOLS, bandwidth_mode

# How many recent learner turns the model sees, per bandwidth mode
HISTORY_TURNS = {"standard": 12, "data_saver": 6, "sms": 4}
# Photos/voice notes are only re-sent to the model for this many recent learner turns
MEDIA_TURNS = 2


def paham_instruction(ctx: ReadonlyContext) -> str:
    """Builds the system instruction from the learner profile on every turn."""
    return build_instruction(ctx.state)


def _is_learner_turn(content: types.Content) -> bool:
    """True for a message typed/sent by the learner (not a tool response)."""
    return content.role == "user" and any(
        part.function_response is None for part in (content.parts or [])
    )


def trim_history(
    contents: list[types.Content], max_turns: int, media_turns: int = MEDIA_TURNS
) -> list[types.Content]:
    """Keeps the last `max_turns` learner turns and drops inline media from older ones.

    Builds new Content objects instead of mutating, so stored session events stay intact.
    Always cuts at a learner turn, so function call/response pairs are never split.
    """
    learner_idx = [i for i, c in enumerate(contents) if _is_learner_turn(c)]
    if len(learner_idx) > max_turns:
        start = learner_idx[-max_turns]
        contents = contents[start:]
        learner_idx = [i - start for i in learner_idx[-max_turns:]]

    keep_media_from = learner_idx[-media_turns] if len(learner_idx) >= media_turns else 0
    trimmed = []
    for i, content in enumerate(contents):
        parts = content.parts or []
        if i >= keep_media_from or not any(p.inline_data for p in parts):
            trimmed.append(content)
            continue
        slim_parts = [p for p in parts if not p.inline_data]
        slim_parts.append(types.Part.from_text(
            text="[An earlier photo or voice note was removed to save data. Ask the learner to resend it if needed.]"
        ))
        trimmed.append(types.Content(role=content.role, parts=slim_parts))
    return trimmed


def fit_request_to_bandwidth(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
    """Applies the per-mode output-token cap and trims the context sent to the model."""
    mode = bandwidth_mode(callback_context.state)
    caps = {
        "standard": CONFIG.max_tokens_standard,
        "data_saver": CONFIG.max_tokens_data_saver,
        "sms": CONFIG.max_tokens_sms,
    }
    if llm_request.config is None:
        llm_request.config = types.GenerateContentConfig()
    llm_request.config.max_output_tokens = caps[mode]
    llm_request.contents = trim_history(llm_request.contents, HISTORY_TURNS[mode])
    return None


# Sentence ends: Latin/Tamil '.', '!', '?' before a space, or CJK and Devanagari full stops
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|[。！？।]")


def end_on_full_sentence(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    """If the token cap cut a reply mid-sentence, trims it back to the last complete sentence."""
    if llm_response.finish_reason != types.FinishReason.MAX_TOKENS or not llm_response.content:
        return None
    texts = [p for p in (llm_response.content.parts or []) if p.text and not p.thought]
    if not texts:
        return None
    last = texts[-1]
    cut = max((m.end() for m in _SENTENCE_END.finditer(last.text)), default=0)
    if cut > len(last.text) // 3:
        last.text = last.text[:cut]
    return llm_response


def _generate_config() -> types.GenerateContentConfig:
    config = types.GenerateContentConfig(temperature=0.4)
    if CONFIG.thinking_level:
        # Thinking tokens count against max_output_tokens; keep them minimal for speed and cost
        config.thinking_config = types.ThinkingConfig(thinking_level=CONFIG.thinking_level)
    return config


# Required ADK entrypoint
root_agent = Agent(
    model=CONFIG.model_name,
    name="paham",
    description=(
        "Localized, multilingual STEM tutor for low-bandwidth learners: explains maths, science "
        "and computing in the student's language with local examples, reads homework photos and "
        "voice notes, and checks practice answers in code."
    ),
    instruction=paham_instruction,
    tools=[search_lesson_notes, *TUTOR_TOOLS],
    generate_content_config=_generate_config(),
    before_model_callback=fit_request_to_bandwidth,
    after_model_callback=end_on_full_sentence,
)
