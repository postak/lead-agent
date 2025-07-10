"""Main application for the Lead Qualification Voice Agent."""

from contextlib import asynccontextmanager

import logging
import os
import sys
from google.cloud.logging_v2.handlers import StructuredLogHandler
import  google.cloud.logging
from  google.cloud.logging import handlers
import dotenv
import fastapi
from google.adk import runners
from src.agents import lead_agent as lead_agent_lib
from src.api import calls
from src.config import settings
from src.handlers import twilio_stream_handler
from src.services import telephony_service as telephony_service_lib

Runner = runners.Runner
telephony_service = telephony_service_lib.telephony_service
lead_agent = lead_agent_lib.agent
WebSocket = fastapi.WebSocket
APIRouter = fastapi.APIRouter
session_service = lead_agent_lib.session_service
memory_service = lead_agent_lib.memory_service
load_dotenv = dotenv.load_dotenv
FastAPI = fastapi.FastAPI
lead_agent = lead_agent_lib.agent
CloudLoggingHandler = handlers.CloudLoggingHandler
setup_logging = handlers.setup_logging

load_dotenv()

def setup_async_logging():
    """Configures a single, asynchronous structured logger for Cloud Run."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    handler = StructuredLogHandler(stream=sys.stdout)
    root_logger.addHandler(handler)

# --- Logging and App Setup ---
setup_async_logging()
instances = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
  logging.info("FastAPI server starting up...")
  runner = Runner(
      app_name=settings.APP_NAME,
      agent=lead_agent,
      session_service=session_service,
      memory_service=memory_service,
  )
  instances["runner"] = runner
  yield
  instances.clear()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.include_router(calls.router)


@app.websocket("/api/ws/twilio_stream")
async def websocket_endpoint(
    websocket: WebSocket,
):
  """Handles the live bidirectional audio stream from Twilio."""
  await websocket.accept()
  logging.info("WEBSOCKET: New connection initiated.")

  handler = twilio_stream_handler.TwilioAgentStream(
      websocket=websocket,
      agent_runner=instances["runner"],
      telephony_service=telephony_service,
  )
  await handler.manage_stream()


@app.get("/")
async def root():
  logging.info("Root path '/' accessed.")
  return {"message": "Lead Qualification Voice Agent API is running."}


if __name__ == "__main__":
  import uvicorn  # pylint: disable=g-import-not-at-top

  uvicorn.run(
      "main:app",
      host="0.0.0.0",
      port=8080,
      reload=True,
      workers=4,
  )
