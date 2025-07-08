"""This module provides a Twilio telephony service."""

import base64
import json
import aiohttp

import logging
from src.config import settings
from twilio import rest
from twilio.base.exceptions import TwilioException
from twilio.twiml import voice_response

Client = rest.Client
Connect = voice_response.Connect
VoiceResponse = voice_response.VoiceResponse
Stream = voice_response.Stream


class TwilioTelephonyService:
  """Manages initiating and controlling calls via the Twilio REST API.

  For live, interactive conversations, this service works in conjunction
  with a WebSocket handler that manages the Twilio Media Stream.
  """

  def __init__(self):
    self.auth = aiohttp.BasicAuth(
        login=settings.TWILIO_ACCOUNT_SID, password=settings.TWILIO_AUTH_TOKEN
    )
    logging.info("SERVICE: Twilio client initialized successfully.")

  async def initiate_call_with_stream(
      self, lead_info: dict[str, str]
  ) -> str | None:
    """Initiates an outbound call using Twilio.

    Instructs Twilio to connect a bidirectional media stream
    to a WebSocket endpoint.

    Args:
        lead_info: A dictionary containing initial context for the agent.

    Returns:
        The Call SID if the call was successfully initiated, None otherwise.
    """
    phone_number = lead_info.get("phone_number")
    lead_id = lead_info.get("lead_id")
    if not phone_number or not lead_id:
      logging.error(
          "SERVICE_ERROR: Phone number or lead_id missing in lead_info."
      )
      return None

    try:
      lead_context_json = json.dumps(lead_info)
      lead_context_b64 = base64.urlsafe_b64encode(
          lead_context_json.encode("utf-8")
      ).decode("utf-8")

      websocket_url = (
          f"{settings.BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://')}/api/ws/twilio_stream"
      )

      logging.info(
          "SERVICE: Using WebSocket stream URL for Twilio: %s",
          websocket_url,
      )

      twiml_response = VoiceResponse()
      connect = Connect()
      stream = Stream(url=websocket_url)
      stream.parameter(name="lead_info", value=lead_context_b64)
      connect.append(stream)
      twiml_response.append(connect)
      status_callback_url = f"{settings.BASE_URL}/api/twilio_status_handler"

      logging.info(
          "SERVICE: Initiating Twilio stream call to %s from %s for lead_id %s",
          phone_number,
          settings.TWILIO_VIRTUAL_PHONE_NUMBER,
          lead_id,
      )

      async with aiohttp.ClientSession(auth=self.auth) as session:
        response = await session.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls.json",
            data={
                "From": settings.TWILIO_VIRTUAL_PHONE_NUMBER,
                "To": phone_number,
                "StatusCallback": status_callback_url,
                "StatusCallbackMethod": "POST",
                "StatusCallbackEvent": [
                    "initiated",
                    "answered",
                    "completed",
                ],
                "Twiml": twiml_response.to_xml(),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        call = await response.json()
        call_sid = call.get("sid")
        logging.info(
            "SERVICE: Twilio call initiated. Call SID: %s and twiml %s. Full call response %s",
            call_sid,
            twiml_response.to_xml(),
            call,
        )
        return call_sid

    except TwilioException as e:
      logging.error(
          "SERVICE_ERROR: Failed to initiate Twilio stream call for lead_id"
          " %s: %s",
          lead_id,
          e,
      )
      return None
    
    except Exception as e:
      logging.exception(e)
      raise e

  async def end_call(self, call_sid: str) -> bool:
    """Terminates an active call using the Twilio REST API.

    Args:
        call_sid: The SID of the call to terminate.

    Returns:
        True if the call was successfully terminated, False otherwise.
    """
    try:
      logging.info(
          "SERVICE: Requesting to terminate call SID %s via REST API.", call_sid
      )
      async with aiohttp.ClientSession(auth=self.auth) as session:
        response = await session.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls/{call_sid}.json",
            data={
                "Status": "completed",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        call = await response.json()

      logging.info(
          "SERVICE: Call %s status updated to '%s' via API.",
          call_sid,
          call.get("status"),
      )
      return True
    except TwilioException as e:
      logging.warning(
          "SERVICE_WARNING: Failed to terminate call %s (it may have already"
          " ended): %s",
          call_sid,
          e,
      )
      return False


# Singleton instance to be used by other parts of the application.
telephony_service = TwilioTelephonyService()
