# Google Agent Development Kit (ADK) - Quickstart Guide

The Google Agent Development Kit (ADK) is an open-source, code-first framework for building, evaluating, and deploying sophisticated AI agents.

## 1. Installation

Requires Python 3.10+:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
pip install google-adk
```

Or using `uv`:
```bash
uv pip install google-adk
```

## 2. Agent Project Structure

An ADK agent package is a Python package containing a mandatory `root_agent` export:

```text
my_agent/
├── __init__.py       # Package marker
├── agent.py          # Defines root_agent and tools
└── .env              # Environment credentials
```

## 3. Minimal Agent (`agent.py`)

```python
from google.adk.agents.llm_agent import Agent

# Tool functions require descriptive docstrings and type annotations
def get_current_time(city: str) -> dict:
    """Returns the current local time in a specified city.

    Args:
        city: Name of the city (e.g. 'Tokyo', 'London').
    """
    return {"status": "success", "city": city, "time": "10:30 AM"}

# root_agent is the entrypoint required by the ADK runtime
root_agent = Agent(
    model="gemini-flash-latest",
    name="root_agent",
    description="Provides real-time information and answers questions.",
    instruction="You are a helpful assistant. Use the 'get_current_time' tool whenever the user asks for time.",
    tools=[get_current_time],
)
```

## 4. Environment Configuration (`.env`)

```bash
# Google AI Studio API Key
GOOGLE_API_KEY="your-api-key-here"

# Or Vertex AI (Google Cloud)
# GOOGLE_GENAI_USE_VERTEXAI="TRUE"
# GOOGLE_CLOUD_PROJECT="my-gcp-project"
# GOOGLE_CLOUD_LOCATION="us-central1"
```

## 5. Running the Agent

### Interactive Terminal CLI
```bash
adk run my_agent
```

### Web Visual Debugger Interface
Run from the directory containing `my_agent/`:
```bash
adk web --port 8000
```
Then navigate to `http://localhost:8000` to inspect traces, call stacks, and streaming tool executions.
*(Note: ADK Web is intended for development and debugging, not production).*
