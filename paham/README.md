# Paham: Localized & Inclusive STEM Learning Agent

*Paham* ("understand") is a lightweight, multimodal STEM tutor, **Cikgu PAHAM**, for rural students in Malaysia (7-18 years). It is built with Google ADK and Gemini Flash-Lite, and works on a basic or shared phone, on a slow or expensive connection, and over SMS.

**How it teaches** (from the master prompt, in `prompts.py`):
- Answers in Bahasa Malaysia by default, with English terms in brackets.
- Builds local kampung analogies with a 3-step framework.
- Uses a 2-phase engine. Phase 1 gives an analogy and a hook question, then waits. Phase 2 gives the exam facts and a clone question.
- Offers emotional support and declines non-STEM questions.

**Lesson notes:** put `.md` or `.txt` files in [`lessons/`](lessons/). They are used as context through the `search_lesson_notes` tool, with no restart needed.

## The problem, and how Paham answers it

| Barrier | What Paham does |
|---|---|
| **Language**: resources assume fluent English | Replies in Bahasa Malaysia by default, and switches only if the student asks. Technical terms come as *local term (English term)*, e.g. "ketumpatan (density)", so learners are ready for English-medium exams. A teacher-reviewable glossary supplies the official school term instead of a made-up translation. |
| **Relevance**: examples are about pizza and subways | The tutor builds every analogy from kampung life (kitchen, kebun, pasar malam, motosikal kapcai). Western and city examples are forbidden in the prompt. |
| **Bandwidth**: AI apps need fast, cheap data | The chat-only web app shell is about **9 KB gzipped**. Photos are shrunk on the device (test worksheet: **416 KB → 22 KB**) and voice notes use 16 kbps Opus (~2 KB/s). Replies are plain text of **0.25-1 KB**. Data-saver mode shortens answers and turns on automatically on 2G or when the phone's Save-Data setting is on. |
| **Device**: no smartphone, or an old one | **SMS channel** for feature phones: replies fit 3 SMS segments (GSM-7 vs UCS-2 counted exactly), typographic characters are swapped so English/Malay/Swahili stay on the cheap encoding, and long answers page on "MORE" / "LAGI" / "ZAIDI" with no extra model call. The web app is plain ES5-era JS with no frameworks and works at 320 px. |
| **Connectivity**: signal comes and goes | Service worker caches the app shell, so it opens with no signal. Typed questions are queued and sent when the signal returns. |
| **Literacy & modality** | Learners can type, **photograph homework**, or **send a voice note**. Gemini reads all three. Every reply has a **Listen** button that uses the phone's built-in text-to-speech, which costs zero extra data. |
| **Cost**: per-token pricing adds up | Flash-Lite with minimal thinking (0 thinking tokens). History is trimmed to recent turns, and old photos are not re-sent to the model. Grading, glossary, lessons and arithmetic run in Python at zero tokens. |
| **Trust**: models make maths mistakes | A safe `calculate` tool does all arithmetic. Practice answers are graded **in code**, never by the model. The answer is hidden from the model until the learner tries twice. |

## Architecture

```
 Learner ──► adk web (dev UI)          ┐
         ──► Lite web app  /api/chat   ├─► ADK Runner ─► paham (LlmAgent, Gemini Flash-Lite)
         ──► SMS gateway   /sms        ┘        │            │ instruction rebuilt per turn from
                                                │            │ learner profile (user: state)
             offline: service worker (app shell) │            ├─ before_model: token cap per mode,
                                                │            │  trim history, drop old media
                                SQLite sessions ┘            ├─ after_model: end on a full sentence
                                (progress persists)          └─ tools (pure Python, 0 tokens):
                                                                set_learner_profile, lookup_stem_term,
                                                                list_topics, get_lesson_card,
                                                                get_practice_question, check_answer,
                                                                get_progress_report, calculate
```

**Why one agent, not a team of agents?** Each extra agent hop is another model round trip. A student on 2G feels every second of that, and pays for every token. So Paham uses a single Flash-Lite agent. Everything that must be *correct* (grading, terminology, arithmetic, curriculum) lives in deterministic tools. The LLM does what only it can do: understand messy multilingual and multimodal input, and explain things kindly in the learner's language.

## Files

```
paham/
  agent.py            root_agent + bandwidth callbacks (ADK entrypoint)
  prompts.py          compact system instruction, rebuilt from the learner profile
  tools.py            deterministic tools: glossary, lessons, grading, progress, calculator
  channels.py         plain-text and SMS shaping (GSM-7/UCS-2 segment math, paging)
  config.py           model and bandwidth budgets (env-overridable)
  demo.py             scripted multilingual demo with token/latency printout
  data/glossary.json  35 STEM terms x 10 languages, with simple definitions
  data/lessons.json   14 micro-lessons, 5 regional examples each, 40 practice items
  lite/server.py      FastAPI: chat web app, multipart chat, SMS webhook
  notes.py            search over uploaded lesson notes (lessons/)
  lessons/            put lesson notes here (.md / .txt)
  lite/static/        index.html (single file), sw.js, manifest, icon
  tests/              29 offline tests (no API key needed)
```

## Running it

All commands run from the repository root. They need `GOOGLE_API_KEY` in the root `.env`, which is already set up for the other agents here.

```bash
# 1. ADK dev UI: pick "paham". Supports image upload and mic recording out of the box.
py -m google.adk.cli web .

# 2. Lite web app + SMS webhook for low-bandwidth learners
py -m uvicorn paham.lite.server:app --host 0.0.0.0 --port 8080
#    open http://localhost:8080 (on a phone: use HTTPS, e.g. a tunnel, so the mic works)

# 3. Scripted demo across languages and channels (prints tool calls, tokens, latency)
py -m paham.demo            # or: py -m paham.demo sms

# 4. Tests (offline, no API key)
py -m unittest discover -s paham/tests -t .
```

`make paham-lite`, `make paham-demo` and `make paham-test` (or `make.bat ...`) wrap the same commands.

**SMS:** point a Twilio-compatible gateway's incoming-message webhook at `POST /sms` (form fields `From`, `Body`; TwiML response). Phone numbers are never stored: learners are keyed by an HMAC of the number. Set `PAHAM_SMS_ID_SECRET` in production.

### Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `PAHAM_MODEL` | `gemini-flash-lite-latest` | Any multimodal Gemini model |
| `PAHAM_THINKING_LEVEL` | `minimal` | Empty string = model default |
| `PAHAM_MAX_TOKENS_STANDARD` / `_DATA_SAVER` / `_SMS` | 900 / 350 / 220 | Output caps per mode |
| `PAHAM_SMS_MAX_SEGMENTS` | 3 | SMS segments per reply page |
| `PAHAM_SESSION_DB` | `paham/.adk/paham_sessions.db` | SQLite session store for the lite server |
| `PAHAM_SMS_ID_SECRET` | dev value | HMAC key for anonymised SMS learner ids |

## Measured on a local run (gemini-flash-lite-latest)

- Latency 2.4-5.7 s per turn, including tool calls. Thinking tokens: 0.
- About 1.9-5 K prompt tokens per turn: tool schemas plus instruction plus trimmed history.
- Photo of homework read correctly, and the learner was coached step by step instead of being handed the answer.
- An English voice note asking for an answer in Swahili got a Swahili reply that used the glossary term "msongamano (density)".
- `check_answer` correctly graded "0.5 ஆம்பியர்" (Tamil), "0,6 g/cm3" (decimal comma, unit with a digit) and "oksijeni" style answers.
- SMS replies stayed within 3 GSM-7 segments, and paging on "ZAIDI" returned instantly.

## Extending

- **Add a language:** add its code to `languages` and to every term in `data/glossary.json` (`test_every_glossary_term_has_every_language` enforces this). Optionally add UI strings to `T` in `lite/static/index.html`. The tutor already speaks it.
- **Add your own lesson notes:** drop `.md`/`.txt` files into `lessons/` (used as context, no code changes).
- **Add a practice lesson card:** append to `data/lessons.json` with an example for all five regions. The tests check the schema and that every practice item accepts its own answer.
- **Local curriculum:** the glossary and lesson packs are plain JSON on purpose, so teachers can review and extend them without touching code.

## Known limits and next steps

- Flash-Lite occasionally slips on details. In one test it wrote "new egg" where it meant "old egg" in Swahili. Facts that matter are pinned in lesson cards and tools, but explanations should still be spot-checked by teachers, especially for lower-resource languages.
- The glossary is a seed: 35 terms in 10 languages, still to be reviewed by native-speaker teachers against each national curriculum.
- Browser voice notes (WebM/Opus) were checked for MIME acceptance by the Gemini API, not with a real Chrome recording.
- SMS paging state is in memory. Use Redis or the database for multi-instance deployments.
- Roadmap: USSD menu channel, a teacher dashboard over `user:progress`, an on-device model (e.g. Gemma) for fully offline tutoring, and community-contributed lesson packs.
