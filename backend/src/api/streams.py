from absl import logging

from fastapi import APIRouter
from fastapi import WebSocket

from google.adk import runners

from src.agents.lead_agent import root_agent
from src.config import settings


from src.handlers import twilio_stream_handler
from src.services import telephony_service as telephony_service_lib

InMemoryRunner = runners.InMemoryRunner
telephony_service = telephony_service_lib.telephony_service

router = APIRouter(prefix="/api", tags=["Streams"])

agent_runner = InMemoryRunner(
    app_name=settings.APP_NAME,
    agent=root_agent,
)


@router.websocket("/ws/twilio_stream")
async def websocket_endpoint(
    websocket: WebSocket,
):
  """Handles the live bidirectional audio stream from Twilio."""
  await websocket.accept()
  logging.info("WEBSOCKET: New connection initiated.")

  handler = twilio_stream_handler.TwilioAgentStream(
      websocket=websocket,
      agent_runner=agent_runner,
      telephony_service=telephony_service,
  )

  await handler.manage_stream()
