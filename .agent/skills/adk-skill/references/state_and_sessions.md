# State Management and Sessions in ADK

ADK provides structured session persistence, audit logging, and state tracking.

## 1. Core Architecture

- **Session**: Tracks conversation history, events, and state across turns for a specific user and application.
- **SessionService**:
  - `InMemorySessionService`: Fast, ephemeral (for tests and local exploration).
  - `DatabaseSessionService`: Relational database backing (Postgres, Cloud SQL) with per-session locking.
  - `VertexAiSessionService`: Managed persistence in Google Cloud.

## 2. State Scopes and Key Prefixes

Keys stored in `state` support naming conventions:
- **No prefix** (e.g. `order_id`): Session-scoped persistent state.
- **`temp:`** (e.g. `temp:last_search_status`): In-memory transient state. Not saved to permanent database storage.
- **`user:`** (e.g. `user:preferred_language`): User-level persistent profile state spanning across sessions.
- **`app:`** (e.g. `app:global_announcement`): Application-level shared state.

## 3. Safe State Mutation Rules

> [!WARNING]
> Never directly mutate `session.state[key] = val` outside of agent/tool execution contexts!
> Direct assignment bypasses event history, drops auditability, and will NOT be committed to persistent stores (like `DatabaseSessionService`).

### Within a Tool Function
Use the injected `ToolContext`:
```python
from google.adk.tools.tool_context import ToolContext

def register_user(username: str, context: ToolContext) -> dict:
    """Registers a user profile."""
    # Read existing state
    current_count = context.state.get("user_count", 0)
    # Mutate state safely (automatically captured in event's state_delta)
    context.state["user_count"] = current_count + 1
    context.state["temp:last_registered"] = username
    return {"status": "ok", "user": username}
```

### Within Agent Callbacks
Use `CallbackContext`:
```python
from google.adk.agents.callback_context import CallbackContext

def on_after_agent_run(context: CallbackContext):
    """Callback after the agent produces an event."""
    context.state["temp:last_run_timestamp"] = "2026-10-17T09:00:00Z"
```

### Outside Managed Invocation (Programmatic)
To update state outside of an agent invocation, record an `Event` with a `state_delta` via `append_event`:
```python
# Use session_service.append_event() to record formal state transitions
```
