"""
Configuration for the Ambient Expense Approval Agent.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv()


@dataclass(frozen=True)
class ExpenseAgentConfig:
    """Configuration settings for expense threshold and model selection."""

    # Dollar threshold: Expenses strictly below this value are auto-approved instantly
    approval_threshold: float = float(os.getenv("EXPENSE_APPROVAL_THRESHOLD", "100.0"))

    # LLM used strictly for risk assessment on high-value expenses (>= threshold)
    model_name: str = os.getenv("EXPENSE_MODEL_NAME", "gemini-3.1-flash-lite")


CONFIG = ExpenseAgentConfig()
