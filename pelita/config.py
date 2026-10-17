"""
Configuration for Pelita, the localized STEM learning agent.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load local environment variables from .env (searches upward from this file)
load_dotenv()

DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class PelitaConfig:
    """Model selection and bandwidth budgets."""

    # Flash-Lite: cheapest, lowest-latency multimodal Gemini tier (reads images + audio)
    model_name: str = os.getenv("PELITA_MODEL", "gemini-flash-lite-latest")
    # Gemini 3 thinking level ('minimal', 'low', ...); empty string = model default
    thinking_level: str = os.getenv("PELITA_THINKING_LEVEL", "minimal")

    # Output-token caps per bandwidth mode (enforced in before_model_callback)
    max_tokens_standard: int = int(os.getenv("PELITA_MAX_TOKENS_STANDARD", "900"))
    max_tokens_data_saver: int = int(os.getenv("PELITA_MAX_TOKENS_DATA_SAVER", "350"))
    max_tokens_sms: int = int(os.getenv("PELITA_MAX_TOKENS_SMS", "220"))

    # SMS replies are cut to this many segments (GSM-7: 153 chars each, UCS-2: 67)
    sms_max_segments: int = int(os.getenv("PELITA_SMS_MAX_SEGMENTS", "3"))

    # Lite web server
    session_db_path: str = os.getenv(
        "PELITA_SESSION_DB", str(Path(__file__).parent / ".adk" / "pelita_sessions.db")
    )
    max_image_bytes: int = int(os.getenv("PELITA_MAX_IMAGE_BYTES", str(1_500_000)))
    max_audio_bytes: int = int(os.getenv("PELITA_MAX_AUDIO_BYTES", str(1_000_000)))


CONFIG = PelitaConfig()
