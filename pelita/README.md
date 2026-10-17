# Pelita: Localized & Inclusive STEM Learning Agent

*Pelita* means "lamp" in Malay and Indonesian. It is a lightweight, multimodal STEM tutor (maths, science, computing/IT) built with Google ADK and Gemini Flash-Lite. It is designed for students that most AI learning tools leave out: rural learners and non-native English speakers who use a basic or shared phone, have a slow or expensive connection, or sometimes no data at all.

## The problem, and how Pelita answers it

| Barrier | What Pelita does |
|---|---|
| **Language**: resources assume fluent English | Replies in the learner's language (10 seeded, any Gemini language works) and mirrors code-switching (Manglish, Taglish, Hinglish). Technical terms come as *local term (English term)*, e.g. "ketumpatan (density)", so learners are ready for English-medium exams. A teacher-reviewable glossary supplies the official school term instead of a made-up translation. |
| **Relevance**: examples are about pizza and subways | Lesson cards carry a checked everyday example for each region (Southeast Asia, South Asia, Africa, Latin America). The tutor localizes names, food, transport and currency. |
| **Bandwidth**: AI apps need fast, cheap data | Web app shell is **10.4 KB gzipped** and the offline study pack is **~7.5 KB**. Photos are shrunk on the device (test worksheet: **416 KB → 22 KB**) and voice notes use 16 kbps Opus (~2 KB/s). Replies are plain text of **0.25-1 KB**. Data-saver mode shortens answers and turns on automatically on 2G or when the phone's Save-Data setting is on. |
| **Device**: no smartphone, or an old one | **SMS channel** for feature phones: replies fit 3 SMS segments (GSM-7 vs UCS-2 counted exactly), typographic characters are swapped so English/Malay/Swahili stay on the cheap encoding, and long answers page on "MORE" / "LAGI" / "ZAIDI" with no extra model call. The web app is plain ES5-era JS with no frameworks and works at 320 px. |
| **Connectivity**: signal comes and goes | Service worker caches the app and the study pack: lessons, glossary and practice (with hints and answers) work fully offline. Typed questions are queued and sent when the signal returns. |
| **Literacy & modality** | Learners can type, **photograph homework**, or **send a voice note**. Gemini reads all three. Every reply has a **Listen** button that uses the phone's built-in text-to-speech, which costs zero extra data. |
| **Cost**: per-token pricing adds up | Flash-Lite with minimal thinking (0 thinking tokens). History is trimmed to recent turns, and old photos are not re-sent to the model. Grading, glossary, lessons and arithmetic run in Python at zero tokens. |
| **Trust**: models make maths mistakes | A safe `calculate` tool does all arithmetic. Practice answers are graded **in code**, never by the model. The answer is hidden from the model until the learner tries twice. |

## Architecture

```
 Learner ──► adk web (dev UI)          ┐
         ──► Lite web app  /api/chat   ├─► ADK Runner ─► pelita (LlmAgent, Gemini Flash-Lite)
         ──► SMS gateway   /sms        ┘        │            │ instruction rebuilt per turn from
                                                │            │ learner profile (user: state)
             offline: /api/pack + service worker│            ├─ before_model: token cap per mode,
                                                │            │  trim history, drop old media
                                SQLite sessions ┘            ├─ after_model: end on a full sentence
                                (progress persists)          └─ tools (pure Python, 0 tokens):
                                                                set_learner_profile, lookup_stem_term,
                                                                list_topics, get_lesson_card,
                                                                get_practice_question, check_answer,
                                                                get_progress_report, calculate
```

**Why one agent, not a team of agents?** Each extra agent hop is another model round trip. A student on 2G feels every second of that, and pays for every token. So Pelita uses a single Flash-Lite agent. Everything that must be *correct* (grading, terminology, arithmetic, curriculum) lives in deterministic tools. The LLM does what only it can do: understand messy multilingual and multimodal input, and explain things kindly in the learner's language.

## Files

```
pelita/
  agent.py            root_agent + bandwidth callbacks (ADK entrypoint)
  prompts.py          compact system instruction, rebuilt from the learner profile
  tools.py            deterministic tools: glossary, lessons, grading, progress, calculator
  channels.py         plain-text and SMS shaping (GSM-7/UCS-2 segment math, paging)
  config.py           model and bandwidth budgets (env-overridable)
  demo.py             scripted multilingual demo with token/latency printout
  data/glossary.json  35 STEM terms x 10 languages, with simple definitions
  data/lessons.json   14 micro-lessons, 5 regional examples each, 40 practice items
  lite/server.py      FastAPI: web app, offline pack, multipart chat, SMS webhook
  lite/static/        index.html (single file), sw.js, manifest, icon
  tests/              29 offline tests (no API key needed)
```

## Running it

All commands run from the repository root. They need `GOOGLE_API_KEY` in the root `.env`, which is already set up for the other agents here.

```bash
# 1. ADK dev UI: pick "pelita". Supports image upload and mic recording out of the box.
py -m google.adk.cli web .

# 2. Lite web app + SMS webhook for low-bandwidth learners
py -m uvicorn pelita.lite.server:app --host 0.0.0.0 --port 8080
#    open http://localhost:8080 (on a phone: use HTTPS, e.g. a tunnel, so the mic works)

# 3. Scripted demo across languages and channels (prints tool calls, tokens, latency)
py -m pelita.demo            # or: py -m pelita.demo sms

# 4. Tests (offline, no API key)
py -m unittest discover -s pelita/tests -t .
```

`make pelita-lite`, `make pelita-demo` and `make pelita-test` (or `make.bat ...`) wrap the same commands.

**SMS:** point a Twilio-compatible gateway's incoming-message webhook at `POST /sms` (form fields `From`, `Body`; TwiML response). Phone numbers are never stored: learners are keyed by an HMAC of the number. Set `PELITA_SMS_ID_SECRET` in production.

### Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `PELITA_MODEL` | `gemini-flash-lite-latest` | Any multimodal Gemini model |
| `PELITA_THINKING_LEVEL` | `minimal` | Empty string = model default |
| `PELITA_MAX_TOKENS_STANDARD` / `_DATA_SAVER` / `_SMS` | 900 / 350 / 220 | Output caps per mode |
| `PELITA_SMS_MAX_SEGMENTS` | 3 | SMS segments per reply page |
| `PELITA_SESSION_DB` | `pelita/.adk/pelita_sessions.db` | SQLite session store for the lite server |
| `PELITA_SMS_ID_SECRET` | dev value | HMAC key for anonymised SMS learner ids |

## Measured on a local run (gemini-flash-lite-latest)

- Latency 2.4-5.7 s per turn, including tool calls. Thinking tokens: 0.
- About 1.9-5 K prompt tokens per turn: tool schemas plus instruction plus trimmed history.
- Photo of homework read correctly, and the learner was coached step by step instead of being handed the answer.
- An English voice note asking for an answer in Swahili got a Swahili reply that used the glossary term "msongamano (density)".
- `check_answer` correctly graded "0.5 ஆம்பியர்" (Tamil), "0,6 g/cm3" (decimal comma, unit with a digit) and "oksijeni" style answers.
- SMS replies stayed within 3 GSM-7 segments, and paging on "ZAIDI" returned instantly.

## Extending

- **Add a language:** add its code to `languages` and to every term in `data/glossary.json` (`test_every_glossary_term_has_every_language` enforces this). Optionally add UI strings to `T` in `lite/static/index.html`. The tutor already speaks it.
- **Add a lesson:** append to `data/lessons.json` with an example for all five regions. The tests check the schema and that every practice item accepts its own answer.
- **Local curriculum:** the glossary and lesson packs are plain JSON on purpose, so teachers can review and extend them without touching code.

## Known limits and next steps

- Flash-Lite occasionally slips on details. In one test it wrote "new egg" where it meant "old egg" in Swahili. Facts that matter are pinned in lesson cards and tools, but explanations should still be spot-checked by teachers, especially for lower-resource languages.
- The glossary is a seed: 35 terms in 10 languages, still to be reviewed by native-speaker teachers against each national curriculum.
- Browser voice notes (WebM/Opus) were checked for MIME acceptance by the Gemini API, not with a real Chrome recording.
- SMS paging state is in memory. Use Redis or the database for multi-instance deployments.
- Roadmap: USSD menu channel, a teacher dashboard over `user:progress`, an on-device model (e.g. Gemma) for fully offline tutoring, and community-contributed lesson packs.
