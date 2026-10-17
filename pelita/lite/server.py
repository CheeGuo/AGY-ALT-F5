"""
Pelita Lite: a tiny HTTP front end for learners on slow networks and basic devices.

Routes
  GET  /            Single-file web app (~25 KB, no frameworks/CDNs; works offline after first visit)
  GET  /sw.js       Service worker: caches the app shell and the offline study pack
  GET  /api/pack    Offline study pack: lesson cards + glossary in one language (~10 KB gzipped)
  POST /api/chat    Multipart: text, optional photo, optional voice note -> plain-text reply
  POST /sms         SMS gateway webhook (Twilio-style From/Body form) -> TwiML reply
  GET  /healthz     Liveness probe

Run:  py -m uvicorn pelita.lite.server:app --host 0.0.0.0 --port 8080
"""

import hashlib
import hmac
import logging
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

from ..agent import root_agent
from ..channels import MORE_KEYWORDS, paginate_sms, to_plain_text
from ..config import CONFIG
from ..tools import load_glossary, load_lessons, normalize_language, region_for

logger = logging.getLogger("pelita.lite")

APP_NAME = "pelita"
STATIC_DIR = Path(__file__).parent / "static"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/aac", "audio/x-m4a", "audio/flac"}
# Phone numbers are never stored: SMS learners are keyed by an HMAC of their number
SMS_ID_SECRET = os.getenv("PELITA_SMS_ID_SECRET", "change-me-in-production").encode()

Path(CONFIG.session_db_path).parent.mkdir(parents=True, exist_ok=True)
session_service = SqliteSessionService(CONFIG.session_db_path)
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

app = FastAPI(title="Pelita Lite", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=400)

# Remaining pages of long SMS replies, served on "MORE" with zero model calls
_sms_pages: dict[str, list[str]] = {}


# ------------------------------------------------------------------------------
# Agent plumbing
# ------------------------------------------------------------------------------
async def ensure_session(user_id: str, session_id: str) -> str:
    """Returns an existing session id for this learner, creating the session if needed."""
    if session_id and await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    ):
        return session_id
    session = await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id or None
    )
    return session.id


async def ask_tutor(user_id: str, session_id: str, parts: list[types.Part], state_delta: dict) -> str:
    """Runs one learner turn through the ADK agent and returns the plain-text reply."""
    reply = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=parts),
        state_delta=state_delta,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            reply.extend(p.text for p in event.content.parts if p.text and not p.thought)
    return to_plain_text("\n".join(reply))


async def read_upload(upload: UploadFile | None, allowed: set[str], max_bytes: int, kind: str) -> types.Part | None:
    """Validates an uploaded photo/voice note and wraps it as an inline Gemini part."""
    if upload is None or not upload.filename:
        return None
    mime = (upload.content_type or "").split(";")[0].strip().lower()
    if mime not in allowed:
        raise HTTPException(415, f"Unsupported {kind} type: {mime or 'unknown'}")
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"{kind.capitalize()} too large (max {max_bytes // 1000} KB)")
    return types.Part.from_bytes(data=data, mime_type=mime) if data else None


# ------------------------------------------------------------------------------
# Web app
# ------------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/icon.svg", include_in_schema=False)
def icon() -> FileResponse:
    return FileResponse(STATIC_DIR / "icon.svg", media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/pack")
def offline_pack(lang: str = "", region: str = "global") -> JSONResponse:
    """Everything a learner needs to keep studying with no connection, in one small download."""
    language = normalize_language(lang)
    region_key = region_for(region)
    glossary = load_glossary()
    terms = glossary["terms"]

    def local(term: str) -> str:
        return terms[term].get(language, "") if language and language != "en" else ""

    lessons = [
        {
            "id": lesson["id"],
            "subject": lesson["subject"],
            "level": lesson["level"],
            "title": lesson["title"],
            "key_idea": lesson["key_idea"],
            "formula": lesson.get("formula", ""),
            "worked_example": lesson["worked_example"],
            "common_mistake": lesson["misconception"],
            "example": lesson["examples"].get(region_key, lesson["examples"]["global"]),
            "terms": [[term, local(term)] for term in lesson.get("terms", [])],
            "practice": [
                {"q": p["question"], "hint": p["hint"], "solution": p["solution"]} for p in lesson["practice"]
            ],
        }
        for lesson in load_lessons().values()
    ]
    words = [
        {"en": key, "local": local(key), "subject": entry["subject"], "definition": entry["definition"]}
        for key, entry in terms.items()
    ]
    return JSONResponse(
        {"language": language or "en", "region": region_key, "lessons": lessons, "glossary": words},
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/api/chat")
async def chat(
    learner_id: str = Form(...),
    session_id: str = Form(""),
    text: str = Form(""),
    data_saver: str = Form("0"),
    language: str = Form(""),
    country: str = Form(""),
    image: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
) -> JSONResponse:
    """One tutoring turn from the lite web app."""
    if not ID_PATTERN.match(learner_id) or (session_id and not ID_PATTERN.match(session_id)):
        raise HTTPException(400, "Invalid learner or session id")

    photo = await read_upload(image, IMAGE_TYPES, CONFIG.max_image_bytes, "photo")
    voice = await read_upload(audio, AUDIO_TYPES, CONFIG.max_audio_bytes, "voice note")
    if not text.strip() and photo is None and voice is None:
        raise HTTPException(400, "Send a question, a photo or a voice note")

    if text.strip():
        parts = [types.Part.from_text(text=text.strip()[:2000])]
    else:
        sent = " and ".join(name for name, part in (("a photo", photo), ("a voice note", voice)) if part)
        parts = [types.Part.from_text(text=f"(The learner sent {sent} without typing anything.)")]
    parts += [part for part in (photo, voice) if part is not None]

    state_delta = {"channel": "lite", "user:data_saver": data_saver in ("1", "true", "on")}
    if language and language != "auto":
        state_delta["user:language"] = normalize_language(language)
    if country:
        state_delta["user:country"] = country[:40]
        state_delta["user:region"] = region_for(country)

    session_id = await ensure_session(learner_id, session_id)
    try:
        reply = await ask_tutor(learner_id, session_id, parts, state_delta)
    except Exception:  # Model/network failure: the client keeps the question and retries
        logger.exception("Tutor call failed")
        raise HTTPException(503, "Tutor temporarily unavailable")
    return JSONResponse({"session_id": session_id, "reply": reply or "..."})


# ------------------------------------------------------------------------------
# SMS (feature phones, no data plan)
# ------------------------------------------------------------------------------
def sms_learner_id(phone: str) -> str:
    digest = hmac.new(SMS_ID_SECRET, phone.strip().encode(), hashlib.sha256).hexdigest()
    return f"sms-{digest[:24]}"


def twiml(message: str) -> Response:
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'
    return Response(body, media_type="application/xml")


@app.post("/sms")
async def sms_webhook(From: str = Form(...), Body: str = Form("")) -> Response:
    """Twilio-compatible webhook. Each phone number gets one long-running tutoring session."""
    learner_id = sms_learner_id(From)
    message = Body.strip()

    if message.casefold() in MORE_KEYWORDS and _sms_pages.get(learner_id):
        return twiml(_sms_pages[learner_id].pop(0))
    if not message:
        return twiml("Pelita: text me any maths, science or computer question, in any language.")

    session_id = await ensure_session(learner_id, learner_id)
    try:
        reply = await ask_tutor(
            learner_id, session_id, [types.Part.from_text(text=message[:600])], {"channel": "sms"}
        )
    except Exception:
        logger.exception("Tutor call failed (SMS)")
        return twiml("Pelita is busy right now. Please send your question again in a few minutes.")

    pages = paginate_sms(reply or "...", CONFIG.sms_max_segments)
    if len(_sms_pages) > 10_000:  # In-memory demo store; use Redis/DB for a real deployment
        _sms_pages.clear()
    _sms_pages[learner_id] = pages[1:]
    return twiml(pages[0])
