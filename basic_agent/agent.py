"""
Basic ADK Agent Example: Weather and City Time Assistant
"""

from google.adk.agents.llm_agent import Agent


def get_weather(city: str) -> dict:
    """Gets the current weather conditions for a specified city.

    Args:
        city: The city name, e.g. 'San Francisco', 'Paris'.
    """
    # Mock data - in real implementations, call a weather API
    return {
        "city": city,
        "temperature_c": 19.5,
        "condition": "Partly Cloudy",
        "humidity": 62,
    }


def get_local_time(city: str) -> dict:
    """Gets the current local time for a specified city.

    Args:
        city: The city name.
    """
    return {
        "city": city,
        "time": "14:35",
        "timezone": "UTC+1",
    }


# Required ADK entrypoint
root_agent = Agent(
    model="gemini-flash-latest",
    name="city_assistant",
    description="Provides real-time weather and time information for global cities.",
    instruction=(
        "You are a friendly city concierge assistant. "
        "Always use 'get_weather' to answer weather questions, and 'get_local_time' for time inquiries. "
        "Present the final answers clearly to the user."
    ),
    tools=[get_weather, get_local_time],
)
