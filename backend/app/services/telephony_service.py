# app/services/telephony_service.py
import json
import base64
from urllib.parse import urlencode
from absl import logging
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse, Say, Stream, Pause

from app.config import settings  # Your application settings


class TwilioTelephonyService:
  """Manages initiating and controlling calls via the Twilio REST API.

  For live, interactive conversations, this service works in conjunction
  with a WebSocket handler that manages the Twilio Media Stream.
  """

  def __init__(self):
    try:
      self.client = Client(
          settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
      )
      logging.info("SERVICE: Twilio client initialized successfully.")
    except Exception as e:
      self.client = None
      logging.critical(
          "SERVICE_ERROR: Failed to initialize Twilio client: %s", e
      )

  def initiate_call_with_stream(
      self, to_phone_number: str, lead_id: str, lead_context: dict | None
  ) -> str | None:
    """Initiates an outbound call using Twilio.

    Instructs Twilio to connect a bidirectional media stream
    to a WebSocket endpoint.

    Args:
        to_phone_number: The E.164 formatted phone number to call.
        lead_id: A unique identifier for the lead/call session.
        lead_context: A dictionary containing initial context for the agent.

    Returns:
        The Call SID if the call was successfully initiated, None otherwise.
    """
    if not self.client:
      logging.error(
          "SERVICE_ERROR: Cannot initiate call, Twilio client not available."
      )
      return None

    try:
      lead_context_json = json.dumps(lead_context)
      lead_context_b64 = base64.urlsafe_b64encode(
          lead_context_json.encode("utf-8")
      ).decode("utf-8")

      query_params_dict = {"lead_id": lead_id, "lead_context": lead_context_b64}
      websocket_url = (
          f"{settings.BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://')}/ws/twilio_stream"
      )

      logging.info(
          "SERVICE: Using WebSocket stream URL for Twilio: %s",
          websocket_url,
      )

      twiml_response = VoiceResponse()
      connect = Connect()
      stream = Stream(url=websocket_url)
      for key, value in query_params_dict.items():
        stream.parameter(name=key, value=value)
      connect.append(stream)
      twiml_response.append(connect)
      status_callback_url = f"{settings.BASE_URL}/api/v1/twilio_status_handler"

      logging.info(
          "SERVICE: Initiating Twilio stream call to %s from %s for lead_id %s",
          to_phone_number,
          settings.TWILIO_VIRTUAL_PHONE_NUMBER,
          lead_id,
      )

      call = self.client.calls.create(
          to=to_phone_number,
          from_=settings.TWILIO_VIRTUAL_PHONE_NUMBER,
          twiml=twiml_response.to_xml(),
          status_callback=status_callback_url,
          status_callback_method="POST",
          status_callback_event=[
              "initiated",
              "ringing",
              "answered",
              "completed",
              "failed",
              "busy",
              "no-answer",
          ],
      )

      logging.info(
          "SERVICE: Twilio call initiated. Call SID: %s and twiml %s",
          call.sid,
          twiml_response.to_xml(),
      )
      return call.sid

    except Exception as e:
      logging.error(
          "SERVICE_ERROR: Failed to initiate Twilio stream call for lead_id"
          " %s: %s",
          lead_id,
          e,
      )
      return None

  def end_call(self, call_sid: str) -> bool:
    """
    Terminates an active call using the Twilio REST API.
    This can be called by your application logic if the agent decides to end the call.
    """
    if not self.client:
      logging.error(
          "SERVICE_ERROR: Cannot end call %s, Twilio client not available.",
          call_sid,
      )
      return False
    try:
      logging.info(
          "SERVICE: Requesting to terminate call SID %s via REST API.", call_sid
      )
      call = self.client.calls(call_sid).update(status="completed")
      logging.info(
          "SERVICE: Call %s status updated to '%s' via API.",
          call_sid,
          call.status,
      )
      return True
    except Exception as e:
      logging.warning(
          "SERVICE_WARNING: Failed to terminate call %s (it may have already"
          " ended): %s",
          call_sid,
          e,
      )
      return False


# Singleton instance to be used by other parts of the application
telephony_service = TwilioTelephonyService()
