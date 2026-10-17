"""
Scripted demo: runs short learner conversations in several languages and channels,
printing each tool call, token usage and latency. Needs GOOGLE_API_KEY in .env.

Run:  py -m paham.demo            (all scenarios)
      py -m paham.demo sms        (one scenario by name)
"""

import asyncio
import sys
import time

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import root_agent

SCENARIOS = {
    "malay": {
        "note": "Form 2 student in Sabah, Malaysia: concept question, then practice graded in code",
        "state": {},
        "turns": ["Cikgu, saya tingkatan 2 dari Sabah. Apa itu ketumpatan? Kenapa kayu terapung?",
                  "Boleh bagi soalan latihan?", "0,6 g/cm3"],
    },
    "tamil": {
        "note": "Tamil speaker on a slow connection (data saver on)",
        "state": {"channel": "lite", "user:data_saver": True},
        "turns": ["மின்தடை என்றால் என்ன? எளிமையாக சொல்லுங்கள்"],
    },
    "taglish": {
        "note": "Code-switching (Taglish) homework help with exact arithmetic",
        "state": {},
        "turns": ["Grade 7 ako sa Pilipinas. Paano i-compute yung 15% discount sa 240 pesos na bag?"],
    },
    "sms": {
        "note": "Swahili learner on a feature phone over SMS",
        "state": {"channel": "sms"},
        "turns": ["Habari, mimi ni mwanafunzi wa kidato cha pili Kenya. Eleza usanisinuru kwa ufupi"],
    },
    "coding": {
        "note": "Hindi-speaking beginner asking about loops",
        "state": {},
        "turns": ["Python में for loop कैसे काम करता है? range(1, 5) क्या देता है?"],
    },
}


async def run_scenario(name: str, scenario: dict) -> None:
    sessions = InMemorySessionService()
    await sessions.create_session(app_name="paham", user_id=name, session_id=name, state=scenario["state"])
    runner = Runner(agent=root_agent, app_name="paham", session_service=sessions)
    print(f"\n{'=' * 72}\n{name.upper()}: {scenario['note']}\n{'=' * 72}")

    for text in scenario["turns"]:
        print(f"\nLEARNER: {text}")
        started, prompt_tokens, output_tokens = time.time(), 0, 0
        async for event in runner.run_async(
            user_id=name, session_id=name,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=text)]),
        ):
            for part in event.content.parts if event.content and event.content.parts else []:
                if part.function_call:
                    print(f"  [tool] {part.function_call.name}({dict(part.function_call.args or {})})")
                elif part.text and event.is_final_response():
                    print(f"PAHAM: {part.text.strip()}")
            if event.usage_metadata:
                prompt_tokens += event.usage_metadata.prompt_token_count or 0
                output_tokens += event.usage_metadata.candidates_token_count or 0
        print(f"  [{time.time() - started:.1f}s | prompt {prompt_tokens} tok | output {output_tokens} tok]")


async def main(names: list[str]) -> None:
    for name in names or SCENARIOS:
        await run_scenario(name, SCENARIOS[name])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Tamil/Hindi/Chinese on Windows consoles
    asyncio.run(main(sys.argv[1:]))
