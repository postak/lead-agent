"""FastAPI router for handling call-related API endpoints."""

import logging
import fastapi
from src.schemas import lead as lead_lib
from src.services import telephony_service as telephony_service_lib

APIRouter = fastapi.APIRouter
Form = fastapi.Form
Response = fastapi.Response
LeadWebhookPayload = lead_lib.LeadWebhookPayload
telephony_service = telephony_service_lib.telephony_service


router = APIRouter(prefix="/api", tags=["Calls"])  # Or adjust as needed


@router.post("/initiate_call", status_code=202)
async def initiate_call_endpoint(payload: LeadWebhookPayload) -> Response:
  """HTTP Webhook to receive a lead and command Twilio to make a call."""
  logging.info("INITIATE_CALL: Received lead for %s", payload.lead_id)
  call_sid = await telephony_service.initiate_call_with_stream(
      lead_info=payload.model_dump(),
  )
  if call_sid:
    return {"status": "call_initiated", "call_sid": call_sid}
  return Response(status_code=500, content="Failed to initiate call")


@router.post("/twilio_status_handler")
async def handle_twilio_call_status(
    call_sid: str = Form(..., alias="CallSid"),
    call_status: str = Form(..., alias="CallStatus"),
    from_: str = Form(None, alias="From"),
    to: str = Form(None, alias="To"),
    call_duration: str = Form(None, alias="CallDuration"),
    sip_response_code: str = Form(None, alias="SipResponseCode"),
):
  """Receives call status updates from Twilio."""
  try:
    logging.info(
        "TWILIO_STATUS_CALLBACK: CallSid: %s, CallStatus: %s, From: %s, To: %s,"
        " Duration: %s",
        call_sid,
        call_status,
        from_,
        to,
        call_duration,
    )

    if call_status == "completed":
      logging.info(
          "Call %s completed. Duration: %s seconds.", call_sid, call_duration
      )
      # TODO: Update database, trigger post-call analysis, notify CRM, etc.
      # Example: await crm_service.log_call_completed(
      #     call_sid, call_duration, from_, to
      # )
    elif call_status == "failed":
      logging.error(
          "Call %s failed. SipResponseCode: %s", call_sid, sip_response_code
      )
      # TODO: Handle failed call, maybe retry logic or alert.
    elif call_status == "no-answer":
      logging.warning("Call %s was not answered.", call_sid)
      # TODO: Update lead status to "No Answer".
    elif call_status == "busy":
      logging.warning("Call %s was busy.", call_sid)
      # TODO: Update lead status to "Busy".
      # Add handling for other statuses like "ringing", "initiated", "canceled"
      # if needed.
  except Exception as e:  # pylint: disable=broad-exception-caught
    logging.exception(
        "TWILIO STATUS HANDLER: Error handling call status: %s", e
    )

  return Response(status_code=200)
