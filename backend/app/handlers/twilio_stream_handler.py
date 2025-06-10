import asyncio
import audioop
import base64
import json
import fastapi

from absl import logging
from typing import AsyncIterable

from app.handlers import utils
from app.services.telephony_service import telephony_service
from app.agents.agent import root_agent
from app.services import telephony_service as telephony_service_lib
from app.config import settings

from google.adk import agents
from google.adk import runners
from google.adk import sessions
from google.adk.agents import run_config as run_config_lib
from google.adk.events import event as event_lib
from google.genai import types


InMemoryRunner = runners.InMemoryRunner
Event = event_lib.Event
RunConfig = run_config_lib.RunConfig
LiveRequestQueue = agents.LiveRequestQueue
WebSocket = fastapi.WebSocket
AgentSession = sessions.Session
TelephonyService = telephony_service_lib.TwilioTelephonyService

ADK_TTS_OUTPUT_SAMPLE_RATE = 24000
TWILIO_EXPECTED_SAMPLE_RATE = 8000


class TwilioAgentStream:
  """Manages a single Twilio Media Stream WebSocket connection and conversation."""

  def __init__(
      self,
      websocket: WebSocket,
      agent_runner: InMemoryRunner,
      telephony_service: TelephonyService,
  ):
    """Initialize the handler with the WebSocket and agent runner."""
    self.websocket = websocket
    self.agent_runner = agent_runner
    self.app_name = settings.APP_NAME
    self.telephony_service = telephony_service

    self.initial_prompt_sent_to_agent = False
    self.terminate_call = False

    self.lead_info: dict = {}
    self.stream_sid: str = ""
    self.call_sid: str = ""
    self.agent_session: AgentSession | None = None
    self.live_events: AsyncIterable[Event | None] | None = None
    self.live_request_queue: LiveRequestQueue | None = None
    logging.info("TwilioStreamHandler initialized.")

  async def _get_managed_agent_session(self, session_id: str) -> AgentSession:
    """Retrieves the session.

    Args:
      session_id: The session ID.

    Returns:
      A Session object.
    """
    managed_session = await self.agent_runner.session_service.get_session(
        session_id=session_id, app_name=self.app_name, user_id=session_id
    )
    if managed_session:
      return managed_session

    return await self.agent_runner.session_service.create_session(
        session_id=session_id,
        app_name=self.app_name,
        user_id=session_id,
    )

  async def start_agent_session(
      self,
      session_id: str,
  ) -> None:
    """Starts a live, streaming agent session for a given session_id.

    Args:
      session_id: The session ID to start the agent session for.

    Returns:
      A tuple containing the live events stream and the request queue.
    """
    session = await self._get_managed_agent_session(session_id=session_id)
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
        )
    )
    run_config = RunConfig(
        response_modalities=["AUDIO"],
        speech_config=speech_config,
        # output_audio_transcription={},
    )
    self.live_request_queue = LiveRequestQueue()
    self.live_events = self.agent_runner.run_live(
        session=session,
        live_request_queue=self.live_request_queue,
        run_config=run_config,
    )
    logging.info("AGENT: Agent is running...")

  async def _terminate_call_after_turn(self, event: Event) -> bool:
    """Check if the agent requested to terminate the call."""
    tool_calls = event.get_function_calls()
    if event.actions and tool_calls:
      for tool_call in tool_calls:
        logging.info("AGENT: called tool: %s", tool_call.name)
        if tool_call.name == "conclude_call":
          self.terminate_call = True

  async def handle_agent_to_twilio_stream(
      self,
  ) -> None:
    """Messages the agent's responses to Twilio."""
    logging.debug(
        "AGENT->TWILIO: Messaging task started for stream %s (CallSid: %s)",
        self.stream_sid,
        self.call_sid,
    )

    turn_counter: int = 1

    try:
      while True:
        async for event in self.live_events:
          await self._terminate_call_after_turn(event)

          if event.turn_complete:
            if self.terminate_call:
              logging.info(
                  "AGENT->TWILIO: Terminating call %s as per agent's request"
                  " (conclude_call).",
                  self.call_sid,
              )
              try:
                self.telephony_service.end_call(self.call_sid)
                await self.websocket.close(
                    code=1000, reason="Agent ended call via tool"
                )
                break
              except Exception as e:
                logging.error(
                    "AGENT->TWILIO: Failed to terminate call %s: %s",
                    self.call_sid,
                    e,
                )

            message = {
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": f"turn_{turn_counter}_complete"},
            }
            await self.websocket.send_text(json.dumps(message))
            turn_counter += 1
            logging.info("AGENT->TWILIO: Turn %s complete.", turn_counter)
            continue

          if event.interrupted:
            message = {
                "event": "clear",
                "streamSid": self.stream_sid,
            }
            logging.info(
                "AGENT->TWILIO: Agent interrupted, clearing stream %s.",
                self.stream_sid,
            )
            await self.websocket.send_text(json.dumps(message))
            continue

          part = (
              event.content and event.content.parts and event.content.parts[0]
          )
          if not part or event.author == "user":
            continue

          part = (
              event.content and event.content.parts and event.content.parts[0]
          )

          is_audio = part.inline_data and part.inline_data.mime_type.startswith(
              "audio/pcm"
          )
          if is_audio:
            pcm_audio_data_bytes = part.inline_data and part.inline_data.data
            mulaw_audio = utils.convert_pcm_audio_to_mulaw(pcm_audio_data_bytes)
            # Send the μ-law audio to Twilio
            message = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": mulaw_audio},
            }
            await self.websocket.send_text(json.dumps(message))
            logging.debug(
                "AGENT->TWILIO: Sent %d bytes of agent audio (8kHz μ-law) to"
                " stream %s.",
                len(mulaw_audio),
                self.stream_sid,
            )

    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.error(
          "Error in handle_agent_to_twilio_stream for stream %s: %s."
          " Attempting to end call...",
          self.stream_sid,
          e,
          exc_info=True,
      )
      self.telephony_service.end_call(self.call_sid)
      await self.websocket.close(code=1011, reason="Agent processing error")

  def send_initial_prompt_to_agent(self):
    """Sends the initial prompt to the agent."""
    if not self.initial_prompt_sent_to_agent:
      initial_prompt = (
          "The phone call has just been answered. Your goal is to qualify"
          f" the lead. The lead's info is: {json.dumps(self.lead_info)}. Please"
          " begin by introducing yourself."
      )
      content = types.Content(
          role="user", parts=[types.Part.from_text(text=initial_prompt)]
      )
      self.live_request_queue.send_content(content=content)
      self.initial_prompt_sent_to_agent = True
      logging.info(
          "TWILIO->AGENT: Initial prompt sent to agent for CallSid %s.",
          self.call_sid,
      )

  async def handle_twilio_to_agent_stream(
      self,
  ) -> None:
    """Listens for messages from Twilio and sends them to the agent."""
    logging.debug(
        "TWILIO->AGENT: Messaging listener task started for CallSid %s,"
        " StreamSid %s.",
        self.call_sid,
        self.stream_sid,
    )
    try:
      self.send_initial_prompt_to_agent()

      while True:
        message_json = await self.websocket.receive_text()
        message = json.loads(message_json)
        event_type = message.get("event")

        if event_type == "start" or event_type == "connected":
          logging.warning(
              "TWILIO->AGENT: Received unexpected '%s' event after initial"
              " setup for CallSid %s.",
              event_type,
              self.call_sid,
          )
          continue

        if event_type == "media":
          decoded_audio = base64.b64decode(message["media"]["payload"])
          pcm_audio = audioop.ulaw2lin(decoded_audio, 2)
          self.live_request_queue.send_realtime(
              types.Blob(data=pcm_audio, mime_type="audio/pcm")
          )
          logging.debug("TWILIO->AGENT: Sent user audio to live request queue.")

        if event_type == "stop" or event_type == "closed":
          logging.info(
              "TWILIO->AGENT: Twilio stream stopped or client ended call."
          )
          self.live_request_queue.close()
          break

        if event_type == "mark":
          logging.debug(
              "TWILIO->AGENT: Received Twilio mark: %s for CallSid %s.",
              message.get("mark", {}).get("name"),
              self.call_sid,
          )
          continue
    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.error(
          "TWILIO->AGENT: Error in handle_twilio_to_agent_stream for CallSid"
          " %s: %s",
          self.call_sid,
          e,
          exc_info=True,
      )
      self.telephony_service.end_call(self.call_sid)
      await self.websocket.close(code=1011, reason="Twilio processing error")

  async def manage_stream(self):
    """Main method that orchestrates the entire WebSocket session."""
    try:
      while True:
        initial_message_json = await self.websocket.receive_text()
        message = json.loads(initial_message_json)
        event_type = message.get("event")
        if event_type != "start":
          continue  # Keep running the loop until "start" event.
        self.stream_sid = message["start"]["streamSid"]
        self.call_sid = message["start"]["callSid"]
        custom_params = message["start"].get("customParameters")
        lead_info_str = custom_params.get("lead_info", "")
        self.lead_info = utils.decode_json_string(lead_info_str)
        logging.info(
            "HANDLER: 'start' event processed. Stream: %s, Call: %s",
            self.stream_sid,
            self.call_sid,
        )
        break  # Exit loop once "start" is received

      if not self.stream_sid:
        await self.websocket.close(
            code=1002, reason="Protocol error: 'start' event not received"
        )
        return

      await self.start_agent_session(session_id=self.stream_sid)

      agent_task = asyncio.create_task(self.handle_agent_to_twilio_stream())
      twilio_task = asyncio.create_task(self.handle_twilio_to_agent_stream())

      await asyncio.wait(
          [agent_task, twilio_task], return_when=asyncio.FIRST_EXCEPTION
      )
    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.exception(
          "WEBSOCKET: Connection error for CallSid %s: %s",
          self.call_sid,
          e,
      )
      if self.call_sid:
        self.telephony_service.end_call(self.call_sid)
    finally:
      logging.info("WEBSOCKET: Closing session.")
      await self.websocket.close(code=1000, reason="Connection closed")
