# Ambient Expense Approval Agent (ADK 2.0 Graph Workflow)

An event-driven ambient expense approval agent built with the **Google Agent Development Kit (ADK 2.0) Graph Workflow API**.

## Graph Architecture

```
[START]
   │
   ▼
[parse_expense_event]  (Decodes Pub/Sub Base64 or plain JSON)
   │
   ▼
[evaluate_threshold_route]  (Pure Python logic: amount < $100)
   ├── "auto_approve" ─────────► [auto_approve_expense]  (Instant, 0 LLM tokens)
   │
   └── "review_required" ──────► [assess_expense_risk]  (gemini-3.1-flash-lite)
                                        │
                                        ▼
                                 [human_approval_gate]  (RequestInput HITL pause)
                                        ├── "approved" ──► [record_approved_outcome]
                                        └── "rejected" ──► [record_rejected_outcome]
```

## Running the Agent

### 1. Test Auto-Approval (< $100)
```bash
py -m google.adk.cli run expense_agent '{"data": {"amount": 42.50, "submitter": "Alice", "category": "Meals", "description": "Team lunch", "date": "2026-10-17"}}'
```

### 2. Test Pub/Sub Base64 Payload (< $100)
```bash
py -m google.adk.cli run expense_agent '{"data": "eyJhbW91bnQiOiA3NS4wLCAic3VibWl0dGVyIjogIkJvYiIsICJjYXRlZ29yeSI6ICJPZmZpY2UiLCAiZGVzY3JpcHRpb24iOiAiU3VwcGxpZXMiLCAiZGF0ZSI6ICIyMDI2LTEwLTE3In0="}'
```

### 3. Test High-Value Expense (>= $100, Triggers LLM + HITL Approval)
```bash
py -m google.adk.cli run expense_agent '{"data": {"amount": 450.00, "submitter": "Charlie", "category": "Travel", "description": "Client executive dinner", "date": "2026-10-17"}}'
```
The agent evaluates risk using `gemini-3.1-flash-lite`, pauses execution, prompts for human decision (`approve` or `reject`), and records the outcome.

### 4. Interactive Web Interface
```bash
py -m google.adk.cli web --port 8000
```
Open `http://localhost:8000` and select `expense_agent` from the dropdown.
