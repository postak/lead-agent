"""Main application for the Lead Qualification Voice Agent."""

import asyncio
import audioop
import base64
import json
from typing import Any, AsyncIterable

from absl import logging
from app.agents.agent import root_agent
from app.api.v1 import twilio_status_handler
from app.schemas.lead import LeadWebhookPayload
from app.services.telephony_service import telephony_service
import dotenv
import fastapi
from google.adk import agents
from google.adk import runners
from google.adk import sessions
from google.adk.agents import run_config as run_config_lib
from google.adk.events import event as event_lib
from google.genai import types


load_dotenv = dotenv.load_dotenv
InMemoryRunner = runners.InMemoryRunner
Event = event_lib.Event
RunConfig = run_config_lib.RunConfig
LiveRequestQueue = agents.LiveRequestQueue
WebSocket = fastapi.WebSocket
Response = fastapi.Response
Request = fastapi.Request
Query = fastapi.Query
FastAPI = fastapi.FastAPI
AgentSession = sessions.Session

load_dotenv()

ADK_TTS_OUTPUT_SAMPLE_RATE = 24000
TWILIO_EXPECTED_SAMPLE_RATE = 8000

# --- Logging and App Setup ---
logging.set_verbosity(logging.INFO)
logging.use_absl_handler()

app = FastAPI(title="Lead Qualification Voice Agent")
app.include_router(twilio_status_handler.router)


runner = InMemoryRunner(
    app_name=app.title,
    agent=root_agent,
)


def _convert_gemini_audio_to_mulaw(audio_data: bytes) -> str:
  """Converts audio bytes to mulaw and returns a base64 string.

  Args:
    audio_data: (bytes) - the raw pcm audio data

  Returns:
    The encoded audio.
  """
  data, _ = audioop.ratecv(
      audio_data,
      2,
      1,
      ADK_TTS_OUTPUT_SAMPLE_RATE,
      TWILIO_EXPECTED_SAMPLE_RATE,
      None,
  )
  mulaw_audio = audioop.lin2ulaw(data, 2)
  encoded_audio = base64.b64encode(mulaw_audio).decode("utf-8")
  return encoded_audio


async def _get_managed_session(session_id: str) -> AgentSession:
  """Retrieves the session.

  Args:
    session_id: The session ID.

  Returns:
    A Session object.
  """
  managed_session = await runner.session_service.get_session(
      session_id=session_id, app_name=app.title, user_id=session_id
  )
  if managed_session:
    return managed_session

  return await runner.session_service.create_session(
      session_id=session_id,
      app_name=app.title,
      user_id=session_id,
  )


async def start_agent_session(
    session_id: str,
) -> tuple[AsyncIterable[Event | None], LiveRequestQueue]:
  """Starts a live, streaming agent session for a given session_id.

  Args:
    session_id: The session ID to start the agent session for.

  Returns:
    A tuple containing the live events stream and the request queue.
  """
  session = await _get_managed_session(session_id)
  speech_config = types.SpeechConfig(
      voice_config=types.VoiceConfig(
          # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
          prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
      )
  )
  run_config = RunConfig(
      response_modalities=["AUDIO"],
      speech_config=speech_config,
      # output_audio_transcription={},
  )
  live_request_queue = LiveRequestQueue()
  live_events = runner.run_live(
      session=session,
      live_request_queue=live_request_queue,
      run_config=run_config,
  )
  logging.info("AGENT: Agent is running...")
  return live_events, live_request_queue


async def agent_to_twilio_messaging(
    websocket: WebSocket,
    live_events: AsyncIterable[Event | None],
    stream_sid: str,
    call_sid: str,
) -> None:
  """Messages the agent's responses to Twilio.

  Args:
    websocket: The WebSocket to send the messages to.
    live_events: The live events stream.
    stream_sid: The stream ID.
    call_sid: The call ID.
  """
  should_terminate_call_after_this_turn = False
  logging.info(
      "AGENT->TWILIO: Messaging task started for stream %s (CallSid: %s)",
      stream_sid,
      call_sid,
  )

  turn_num = 1

  try:
    while True:
      async for event in live_events:
        tool_calls = event.get_function_calls()
        if event.actions and tool_calls:
          for tool_call in tool_calls:
            if tool_call.name == "conclude_call":
              logging.info(
                  "AGENT->TWILIO: Agent initiated 'conclude_call. Call will"
                  " be terminated after current turn completes.",
              )
              should_terminate_call_after_this_turn = True

        if event.turn_complete:
          logging.info(
              "AGENT->TWILIO: Agent turn complete for stream %s.", stream_sid
          )
          if should_terminate_call_after_this_turn:
            logging.info(
                "AGENT->TWILIO: Terminating call %s as per agent's request"
                " (conclude_call).",
                call_sid,
            )
            telephony_service.end_call(call_sid)
            await websocket.close(code=1000, reason="Agent ended call via tool")
          message = {
              "event": "mark",
              "streamSid": stream_sid,
              "mark": {"name": f"turn_{turn_num}complete"},
          }
          await websocket.send_text(json.dumps(message))
          turn_num += 1
          continue
        if event.interrupted:
          message = {
              "event": "clear",
              "streamSid": stream_sid,
          }
          await websocket.send_text(json.dumps(message))
          continue
        part = event.content and event.content.parts and event.content.parts[0]
        if not part:
          continue
        if event.author == "user":
          continue
        part = event.content and event.content.parts and event.content.parts[0]

        is_audio = part.inline_data and part.inline_data.mime_type.startswith(
            "audio/pcm"
        )
        if is_audio:
          pcm_audio_data_bytes = part.inline_data and part.inline_data.data
          mulaw_audio = _convert_gemini_audio_to_mulaw(pcm_audio_data_bytes)
          # Send the μ-law audio to Twilio
          message = {
              "event": "media",
              "streamSid": stream_sid,
              "media": {"payload": mulaw_audio},
          }
          await websocket.send_text(json.dumps(message))
          logging.info(
              "AGENT->TWILIO: Sent %d bytes of agent audio (8kHz μ-law) for"
              " stream %s.",
              len(mulaw_audio),
              stream_sid,
          )
          continue

  except Exception as e:  # pylint: disable=broad-exception-caught
    logging.error(
        "Error in agent_to_twilio_messaging for stream %s (CallSid %s): %s."
        " Attempting to end call...",
        stream_sid,
        call_sid,
        e,
        exc_info=True,
    )
    telephony_service.end_call(call_sid)
    await websocket.close(code=1011, reason="Agent processing error")


async def twilio_to_agent_messaging(
    websocket: WebSocket,
    live_request_queue: LiveRequestQueue,
    lead_info: dict[str, Any],
    stream_sid: str,
    call_sid: str,
) -> None:
  """Listens for messages from Twilio and sends them to the agent.

  Args:
    websocket: The WebSocket to receive the messages from.
    live_request_queue: The live request queue to send the messages to.
    lead_info: The lead info to send to the agent.
    stream_sid: The stream ID.
    call_sid: The call ID.
  """
  logging.info(
      "TWILIO->AGENT: Messaging listener task started for CallSid %s,"
      " StreamSid %s.",
      call_sid,
      stream_sid,
  )
  initial_prompt_sent_to_agent = False
  try:
    if not initial_prompt_sent_to_agent:
      logging.info(
          "TWILIO->AGENT: Processing initial 'start' context for CallSid %s.",
          call_sid,
      )
      initial_prompt = (
          "The phone call has just been answered. Your goal is to qualify"
          f" the lead. The lead's info is: {json.dumps(lead_info)}. Please"
          " begin by introducing yourself."
      )
      content = types.Content(
          role="user", parts=[types.Part.from_text(text=initial_prompt)]
      )
      live_request_queue.send_content(content=content)
      initial_prompt_sent_to_agent = True
      logging.info(
          "TWILIO->AGENT: Initial prompt sent to agent for CallSid %s.",
          call_sid,
      )

    while True:
      message_json = await websocket.receive_text()
      message = json.loads(message_json)
      event_type = message.get("event")
      if event_type == "start" or event_type == "connected":
        logging.warning(
            "TWILIO->AGENT: Received unexpected '%s' event after initial setup"
            " for CallSid %s.",
            event_type,
            call_sid,
        )
        continue
      elif event_type == "media":
        decoded_audio = base64.b64decode(message["media"]["payload"])
        pcm_audio = audioop.ulaw2lin(decoded_audio, 2)
        live_request_queue.send_realtime(
            types.Blob(data=pcm_audio, mime_type="audio/pcm")
        )
        logging.info("TWILIO->AGENT: Sent user audio to live request queue.")
      elif event_type == "stop" or event_type == "closed":
        logging.info("TWILIO->AGENT: Twilio stream stopped.")
        live_request_queue.close()
        break
      elif event_type == "mark":
        logging.info(
            "TWILIO->AGENT: Received Twilio mark: %s for CallSid %s.",
            message.get("mark", {}).get("name"),
            call_sid,
        )
        continue
      else:
        logging.warning(
            "TWILIO->AGENT: Received unknown subsequent event type '%s' for"
            " CallSid %s: %s",
            event_type,
            call_sid,
            message,
        )
  except asyncio.CancelledError:
    logging.info(
        "TWILIO->AGENT: Messaging task cancelled for CallSid %s.", call_sid
    )
  except Exception as e:  # pylint: disable=broad-exception-caught
    logging.error(
        "TWILIO->AGENT: Error in twilio_to_agent_messaging for CallSid %s: %s",
        call_sid,
        e,
        exc_info=True,
    )

  finally:
    live_request_queue.close()
    logging.info(
        "TWILIO->AGENT: Messaging task finished for CallSid %s.", call_sid
    )


# --- API Endpoints ---
@app.post("/api/v1/initiate_call", status_code=202)
async def initiate_call_endpoint(payload: LeadWebhookPayload) -> Response:
  """HTTP Webhook to receive a lead and command Twilio to make a call."""
  logging.info("INITIATE_CALL: Received lead for %s", payload.full_name)
  call_sid = telephony_service.initiate_call_with_stream(
      to_phone_number=payload.phone_number,
      lead_id=payload.lead_id,
      lead_context=payload.model_dump(),
  )
  if call_sid:
    return {"status": "call_initiated", "call_sid": call_sid}
  return Response(status_code=500, content="Failed to initiate call")


@app.websocket("/ws/twilio_stream")
async def websocket_endpoint(
    websocket: WebSocket,
):
  """Handles the live bidirectional audio stream from Twilio."""
  await websocket.accept()
  logging.info("WEBSOCKET: New connection initiated.")

  stream_sid_from_twilio = ""
  call_sid_from_twilio = ""
  initial_start_message_payload = None
  initial_messages_processed_count = 0
  lead_id = ""
  decoded_lead_info = {}

  try:
    while initial_messages_processed_count < 5:
      message_json = await websocket.receive_text()
      message = json.loads(message_json)
      initial_messages_processed_count += 1
      event_type = message.get("event")

      if event_type == "start":
        start_payload = message["start"]
        stream_sid_from_twilio = start_payload["streamSid"]
        call_sid_from_twilio = start_payload["callSid"]

        custom_params = start_payload.get("customParameters")
        lead_id = custom_params.get("lead_id", "Undefined")
        lead_context = custom_params.get("lead_context", "")

        initial_start_message_payload = message
        try:
          decoded_lead_context_json = base64.urlsafe_b64decode(
              lead_context
          ).decode("utf-8")
          decoded_lead_info = json.loads(decoded_lead_context_json)
        except json.JSONDecodeError as e:
          logging.error(
              "WEBSOCKET: Could not decode lead_context JSON: %s. Error: %s",
              lead_context,
              e,
          )
        logging.info(
            "WEBSOCKET: 'start' event received. Stream %s for CallSid %s.",
            stream_sid_from_twilio,
            call_sid_from_twilio,
        )
        break
      elif event_type == "connected":
        logging.info(
            "WEBSOCKET: Received 'connected' event. Continuing to wait for"
            " 'start' event.",
        )
      else:
        logging.warning(
            "WEBSOCKET: Expected 'start' or 'connected' event during handshake,"
            " but received '%s'. Ignoring. Message: %s",
            event_type,
            message,
        )
    if not initial_start_message_payload:
      logging.error(
          "WEBSOCKET: Did not receive 'start' event after %d messages."
          " Closing.",
          initial_messages_processed_count,
      )
      await websocket.close(
          code=1002, reason="Protocol error: 'start' event not received"
      )
      return

    live_events, live_request_queue = await start_agent_session(
        session_id=stream_sid_from_twilio
    )

    agent_task = asyncio.create_task(
        agent_to_twilio_messaging(
            websocket, live_events, stream_sid_from_twilio, call_sid_from_twilio
        )
    )

    twilio_task = asyncio.create_task(
        twilio_to_agent_messaging(
            websocket,
            live_request_queue,
            decoded_lead_info,
            stream_sid_from_twilio,
            call_sid_from_twilio,
        )
    )

    await asyncio.wait(
        [agent_task, twilio_task],
        return_when=asyncio.FIRST_EXCEPTION,
    )

  except Exception as e:  # pylint: disable=broad-exception-caught
    logging.error(
        "WEBSOCKET: Connection error for CallSid %s: %s",
        call_sid_from_twilio,
        e,
    )
    if call_sid_from_twilio:
      telephony_service.end_call(call_sid_from_twilio)
  finally:
    logging.info(
        "WEBSOCKET: Connection closed for CallSid %s.",
        call_sid_from_twilio,
    )


# Root endpoint for health check or basic info
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
  )
