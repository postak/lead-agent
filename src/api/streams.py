"""FastAPI router for handling Twilio stream."""

from absl import logging
import fastapi
from google.adk import runners
from src.agents import lead_agent as lead_agent_lib
from src.config import settings
from src.handlers import twilio_stream_handler
from src.services import telephony_service as telephony_service_lib

InMemoryRunner = runners.InMemoryRunner
telephony_service = telephony_service_lib.telephony_service
lead_agent = lead_agent_lib.agent
WebSocket = fastapi.WebSocket
APIRouter = fastapi.APIRouter


router = APIRouter(prefix="/api", tags=["Streams"])

agent_runner = InMemoryRunner(
    app_name=settings.APP_NAME,
    agent=lead_agent,
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
