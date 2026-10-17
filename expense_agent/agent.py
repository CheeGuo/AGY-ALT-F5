"""
Ambient Expense-Approval Agent (ADK 2.0 Graph Workflow API)

Architecture:
- Function nodes wired together with explicit graph edges.
- Threshold & routing logic in pure Python code (no LLM tokens spent on basic rules).
- LLM (gemini-3.1-flash-lite) evaluates risk factors ONLY on expenses >= threshold.
- Human-in-the-Loop (HITL) pause using RequestInput before recording outcome.
- Emits both structured `output` for APIs/workflows and `content` for CLI/Web UI chat.
"""

import base64
import datetime
import json
import re
from typing import Any

from google import genai
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Workflow, node
from google.genai import types

from .config import CONFIG


# ------------------------------------------------------------------------------
# Node 1: Event Parsing & Extraction
# ------------------------------------------------------------------------------
def parse_expense_event(ctx: Context, node_input: Any) -> dict:
    """Parses incoming expense event payload.

    Supports:
    - Base64-encoded JSON sitting under a 'data' key (real Google Cloud Pub/Sub)
    - Plain JSON object or dict sitting under a 'data' key (local testing)
    - Direct JSON string or dictionary representation
    """
    raw_payload = node_input

    # Extract text content if input arrives as an ADK Content object
    if hasattr(raw_payload, "parts"):
        for part in raw_payload.parts:
            if hasattr(part, "text") and part.text:
                raw_payload = part.text
                break

    # Parse JSON string if necessary
    if isinstance(raw_payload, str):
        try:
            raw_payload = json.loads(raw_payload)
        except Exception:
            pass

    # Inspect 'data' key (Pub/Sub envelope or local envelope)
    if isinstance(raw_payload, dict) and "data" in raw_payload:
        data_field = raw_payload["data"]
        if isinstance(data_field, str):
            # Attempt base64 decoding (Pub/Sub standard)
            try:
                decoded_bytes = base64.b64decode(data_field, validate=True)
                raw_payload = json.loads(decoded_bytes.decode("utf-8"))
            except Exception:
                # Fallback to direct string parse if not base64
                raw_payload = json.loads(data_field)
        elif isinstance(data_field, dict):
            raw_payload = data_field

    if not isinstance(raw_payload, dict):
        # Support session resume queries (e.g. 'approve' or 'reject')
        if "expense" in ctx.state:
            return ctx.state["expense"]
        raise ValueError(f"Unable to parse expense payload into dictionary: {node_input}")

    # Extract required canonical expense fields
    expense = {
        "amount": float(raw_payload.get("amount", 0.0)),
        "submitter": str(raw_payload.get("submitter", "Unknown")),
        "category": str(raw_payload.get("category", "General")),
        "description": str(raw_payload.get("description", "No description")),
        "date": str(raw_payload.get("date", datetime.date.today().isoformat())),
    }

    # Store in context state for auditability
    ctx.state["expense"] = expense
    return expense


# ------------------------------------------------------------------------------
# Node 2: Rule-Based Threshold Routing (Pure Python)
# ------------------------------------------------------------------------------
def evaluate_threshold_route(ctx: Context, node_input: dict) -> Event:
    """Evaluates threshold in pure Python.

    Routes:
    - 'auto_approve' if amount < CONFIG.approval_threshold (Under $100)
    - 'review_required' if amount >= CONFIG.approval_threshold ($100 or more)
    """
    amount = node_input.get("amount", 0.0)

    if amount < CONFIG.approval_threshold:
        return Event(
            output=node_input,
            route="auto_approve",
            state={"route_decision": "AUTO_APPROVE_PATH"},
        )
    else:
        return Event(
            output=node_input,
            route="review_required",
            state={"route_decision": "HUMAN_REVIEW_PATH"},
        )


# ------------------------------------------------------------------------------
# Node 3: Instant Auto-Approval (Zero LLM Tokens)
# ------------------------------------------------------------------------------
def auto_approve_expense(ctx: Context, node_input: dict) -> Event:
    """Instantly approves expenses under the threshold without LLM involvement."""
    outcome = {
        "status": "APPROVED",
        "decision": "AUTO_APPROVED",
        "reason": f"Amount ${node_input['amount']:.2f} is under ${CONFIG.approval_threshold:.2f} threshold.",
        "expense": node_input,
        "risk_assessment": None,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    ctx.state["outcome"] = outcome

    message = (
        f"[AUTO-APPROVED] Expense of ${node_input['amount']:.2f} for '{node_input['description']}' "
        f"submitted by {node_input['submitter']} ({node_input['category']}) has been automatically approved "
        f"(below ${CONFIG.approval_threshold:.2f} threshold)."
    )

    return Event(
        content=types.Content(parts=[types.Part.from_text(text=message)]),
        output=outcome,
    )


# ------------------------------------------------------------------------------
# Security Controls: PII Scrubbing & Prompt Injection Defense
# ------------------------------------------------------------------------------
SSN_REGEX = re.compile(r"\b(?:\d{3}[-\s]\d{2}[-\s]\d{4}|\d{9})\b")
CREDIT_CARD_REGEX = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{4}\b|"
    r"\b\d{4}[-\s]\d{6}[-\s]\d{5}\b"
)

PROMPT_INJECTION_RULES = [
    (
        r"(?i)\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|prior\s+|previous\s+)?(?:instructions|rules|prompts|guidelines|policies|checks)\b",
        "instruction_override",
    ),
    (
        r"(?i)\b(?:system\s+override|admin\s+override|developer\s+mode|dan\s+mode|root\s+access|sudo\s+mode)\b",
        "privilege_escalation",
    ),
    (
        r"(?i)\b(?:force|auto[- ]?|always|instantly)\s*approve\b",
        "forced_approval",
    ),
    (
        r"(?i)\b(?:bypass|skip|evade)\s+(?:all\s+)?(?:the\s+)?(?:rules?|checks?|validations?|audits?|thresholds?|approvals?|policies)\b",
        "rule_bypass",
    ),
    (
        r"(?i)\bdo\s+not\s+(?:flag|review|report|audit|check)\b",
        "audit_suppression",
    ),
    (
        r"(?i)\bmark\s+(?:this\s+)?(?:as\s+)?(?:approved|low\s+risk|compliant|safe)\b",
        "status_tampering",
    ),
    (
        r"(?i)\boverride\s+(?:the\s+)?(?:rules?|thresholds?|limits?|policies|decisions?)\b",
        "rule_override",
    ),
    (
        r"(?i)(?:<\s*system\s*>|\[system\]|```system|\binstruction:\s*approve\b)",
        "structural_injection_tag",
    ),
]


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """Scrubs SSNs and credit card numbers from text and tracks redacted categories."""
    redacted_categories: list[str] = []
    sanitized = text

    if SSN_REGEX.search(sanitized):
        sanitized = SSN_REGEX.sub("[REDACTED_SSN]", sanitized)
        redacted_categories.append("SSN")

    if CREDIT_CARD_REGEX.search(sanitized):
        sanitized = CREDIT_CARD_REGEX.sub("[REDACTED_CREDIT_CARD]", sanitized)
        redacted_categories.append("CREDIT_CARD")

    return sanitized, redacted_categories


def detect_prompt_injection(text: str) -> list[str]:
    """Scans text for prompt injection vectors attempting to force approval or bypass rules."""
    flags: list[str] = []
    for pattern, rule_name in PROMPT_INJECTION_RULES:
        if re.search(pattern, text):
            flags.append(rule_name)
    return flags


# ------------------------------------------------------------------------------
# Node 4: Security Checkpoint
# ------------------------------------------------------------------------------
def security_checkpoint(ctx: Context, node_input: dict) -> Event:
    """Security Checkpoint: Enforces PII scrubbing and prompt injection defense.

    1. Scrubs SSNs and credit-card numbers from description so they never reach
       the LLM, logs, or human approval payload. Remembers redacted categories.
    2. Defends against prompt injection: If instructions attempting to force
       auto-approval or bypass rules are detected, blocks LLM review completely,
       flags a security event, and routes directly to human review.

    Routes:
    - 'clean': Passes sanitized expense to LLM risk auditor.
    - 'security_flagged': Bypasses LLM and routes directly to human approval gate.
    """
    raw_description = node_input.get("description", "")

    # 1. Scrub PII
    sanitized_desc, redacted_categories = scrub_pii(raw_description)

    # Build sanitized expense payload (guarantees model & logs never see raw PII)
    sanitized_expense = dict(node_input)
    sanitized_expense["description"] = sanitized_desc

    # Update state with sanitized data and recorded categories
    ctx.state["expense"] = sanitized_expense
    if redacted_categories:
        ctx.state["redacted_categories"] = redacted_categories

    # 2. Check for Prompt Injection / Rule Bypass
    injection_flags = detect_prompt_injection(raw_description)

    if injection_flags:
        # Prompt injection detected: Flag security event and bypass LLM!
        security_event = {
            "status": "SECURITY_FLAGGED",
            "reason": "Prompt injection / policy bypass attempt detected.",
            "flags": injection_flags,
            "redacted_categories": redacted_categories,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        ctx.state["security_event"] = security_event

        security_alert = (
            f"[SECURITY ALERT: PROMPT INJECTION DETECTED]\n"
            f"Adversarial instructions attempting to force auto-approval or bypass policies were detected.\n"
            f"- Security Flags: {', '.join(injection_flags)}\n"
            f"- Action Taken: LLM auditor was BYPASSED to prevent model manipulation.\n"
            f"- Routing: Escalated directly to human reviewer as a security event."
        )
        if redacted_categories:
            security_alert += f"\n- Redacted PII Categories: {', '.join(redacted_categories)}"

        return Event(
            output={
                "expense": sanitized_expense,
                "risk_assessment": security_alert,
                "security_flags": injection_flags,
                "redacted_categories": redacted_categories,
            },
            route="security_flagged",
            state={"security_flag": True},
        )

    # Clean expense: continue to LLM reviewer with sanitized payload
    return Event(
        output=sanitized_expense,
        route="clean",
        state={"security_flag": False},
    )


# ------------------------------------------------------------------------------
# Node 5: LLM Risk Assessment (gemini-3.1-flash-lite)
# ------------------------------------------------------------------------------
def assess_expense_risk(ctx: Context, node_input: dict) -> dict:
    """Analyzes sanitized high-value expenses using the configured LLM for risk factors."""
    client = genai.Client()
    prompt = f"""You are a corporate financial compliance auditor.
Analyze the following expense report for policy risk factors (e.g. lavish spending, unusual categories, missing context):

Expense Details:
- Submitter: {node_input['submitter']}
- Amount: ${node_input['amount']:.2f}
- Category: {node_input['category']}
- Description: {node_input['description']}
- Date: {node_input['date']}

Provide:
1. Assigned Risk Level: (LOW, MEDIUM, or HIGH)
2. Risk Summary: (1-2 sentences highlighting potential flags or compliance issues)"""

    response = client.models.generate_content(
        model=CONFIG.model_name,
        contents=prompt,
    )
    risk_summary = response.text.strip() if response.text else "No specific risk factors flagged."

    assessment = {
        "expense": node_input,
        "risk_assessment": risk_summary,
        "security_flags": [],
        "redacted_categories": ctx.state.get("redacted_categories", []),
    }
    ctx.state["risk_assessment"] = risk_summary
    return assessment


# ------------------------------------------------------------------------------
# Node 6: Human-in-the-Loop (HITL) Gate with RequestInput
# ------------------------------------------------------------------------------
@node(rerun_on_resume=True)
async def human_approval_gate(ctx: Context, node_input: dict):
    """Pauses workflow execution with RequestInput waiting for human decision.

    On resume, evaluates human decision and routes to 'approved' or 'rejected'.
    """
    # Check if we have received a response from the human reviewer
    user_decision = None
    if ctx.resume_inputs:
        user_decision = ctx.resume_inputs.get("approval_decision")
        if not user_decision:
            user_decision = next(iter(ctx.resume_inputs.values()), None)

    if not user_decision:
        expense = node_input["expense"]
        risk = node_input["risk_assessment"]
        redacted = node_input.get("redacted_categories") or ctx.state.get("redacted_categories", [])
        redacted_info = f" | Redacted PII: {', '.join(redacted)}" if redacted else ""

        prompt_message = (
            f"[ACTION REQUIRED: EXPENSE APPROVAL]\n"
            f"Amount: ${expense['amount']:.2f} | Submitter: {expense['submitter']} | Category: {expense['category']}{redacted_info}\n"
            f"Description: {expense['description']}\n"
            f"Date: {expense['date']}\n\n"
            f"Review / Risk Assessment:\n{risk}\n\n"
            f"Please approve or reject this expense (Type 'approve' or 'reject'):"
        )
        yield RequestInput(
            interrupt_id="approval_decision",
            message=prompt_message,
        )
        return

    # Process resumed decision
    decision_clean = str(user_decision).strip().lower()
    is_approved = decision_clean in ("approve", "approved", "yes", "y", "accept")
    route = "approved" if is_approved else "rejected"

    yield Event(
        output={
            "expense": node_input["expense"],
            "risk_assessment": node_input["risk_assessment"],
            "security_flags": node_input.get("security_flags", []),
            "redacted_categories": node_input.get("redacted_categories", []),
            "decision": "APPROVED" if is_approved else "REJECTED",
            "reviewer_input": str(user_decision),
        },
        route=route,
        state={"human_decision": decision_clean},
    )


# ------------------------------------------------------------------------------
# Node 7A: Record Approved Outcome
# ------------------------------------------------------------------------------
def record_approved_outcome(ctx: Context, node_input: dict) -> Event:
    """Records formal approval outcome following human approval."""
    outcome = {
        "status": "APPROVED",
        "decision": "HUMAN_APPROVED",
        "expense": node_input["expense"],
        "risk_assessment": node_input["risk_assessment"],
        "security_flags": node_input.get("security_flags", []),
        "redacted_categories": node_input.get("redacted_categories", []),
        "reviewer_input": node_input.get("reviewer_input"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    ctx.state["outcome"] = outcome

    message = (
        f"[HUMAN-APPROVED] Expense of ${node_input['expense']['amount']:.2f} for "
        f"'{node_input['expense']['description']}' has been officially APPROVED by human reviewer."
    )

    return Event(
        content=types.Content(parts=[types.Part.from_text(text=message)]),
        output=outcome,
    )


# ------------------------------------------------------------------------------
# Node 7B: Record Rejected Outcome
# ------------------------------------------------------------------------------
def record_rejected_outcome(ctx: Context, node_input: dict) -> Event:
    """Records formal rejection outcome following human rejection."""
    outcome = {
        "status": "REJECTED",
        "decision": "HUMAN_REJECTED",
        "expense": node_input["expense"],
        "risk_assessment": node_input["risk_assessment"],
        "security_flags": node_input.get("security_flags", []),
        "redacted_categories": node_input.get("redacted_categories", []),
        "reviewer_input": node_input.get("reviewer_input"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    ctx.state["outcome"] = outcome

    message = (
        f"[HUMAN-REJECTED] Expense of ${node_input['expense']['amount']:.2f} for "
        f"'{node_input['expense']['description']}' has been REJECTED by human reviewer."
    )

    return Event(
        content=types.Content(parts=[types.Part.from_text(text=message)]),
        output=outcome,
    )


# ------------------------------------------------------------------------------
# ADK 2.0 Graph Workflow Definition
# ------------------------------------------------------------------------------
root_agent = Workflow(
    name="ambient_expense_agent",
    description="Ambient expense-approval workflow with threshold routing, security checkpoint, LLM risk review, and HITL gate.",
    edges=[
        # Entrypoint -> Event Parsing
        (START, parse_expense_event),
        # Parsing -> Python Threshold Evaluation
        (parse_expense_event, evaluate_threshold_route),
        # Conditional Branching based on Threshold ($100)
        (
            evaluate_threshold_route,
            {
                "auto_approve": auto_approve_expense,
                "review_required": security_checkpoint,
            },
        ),
        # Security Checkpoint Branching:
        # - "clean": continues to LLM risk reviewer
        # - "security_flagged": bypasses LLM straight to human review
        (
            security_checkpoint,
            {
                "clean": assess_expense_risk,
                "security_flagged": human_approval_gate,
            },
        ),
        # Clean path: LLM Risk Assessment -> Human Approval Gate (RequestInput)
        (assess_expense_risk, human_approval_gate),
        # Conditional Branching based on Human Decision
        (
            human_approval_gate,
            {
                "approved": record_approved_outcome,
                "rejected": record_rejected_outcome,
            },
        ),
    ],
)
