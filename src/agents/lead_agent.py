"""Defines the ADK-native Agent for lead qualification."""

import logging
import json
from google.adk import agents
from google.adk import memory
from google.adk import sessions
from src.tools import lead_tools
from src.tools import telephony_tools
from src.tools import calendar_tools
from src.prompts import instructions

InMemorySessionService = sessions.InMemorySessionService
InMemoryMemoryService = memory.InMemoryMemoryService
build_lead_quality_record = lead_tools.build_lead_quality_record
conclude_call = telephony_tools.conclude_call
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()
get_current_time = calendar_tools.get_current_time
create_event = calendar_tools.create_event
edit_event = calendar_tools.edit_event
delete_event = calendar_tools.delete_event
list_events = calendar_tools.list_events

_MODEL = "gemini-live-2.5-flash-preview"  # "gemini-2.0-flash-live-001"


# Singleton instance to be used by other parts of the application.
agent = agents.Agent(
    name="Alex",
    description=(
        "A conversational agent that qualifies leads over the phone by asking"
        " questions based on the BANT framework."
    ),
    model=_MODEL,
    instruction=instructions.get_instructions(json.dumps(get_current_time())),
    tools=[
        build_lead_quality_record,
        conclude_call,
        create_event,
        edit_event,
        delete_event,
        list_events,
    ],
)

logging.info("AGENT: Declarative Agent '%s' defined.", agent.name)
