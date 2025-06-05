# app/tools/record_qualification_data.py
from absl import logging
from app.services.crm_service import crm_service  # Using our mocked service


def build_lead_quality_record(
    lead_id: str,
    is_qualified: bool,
    summary: str,
    timeline: str,
    needs: str,
    has_authority: bool,
    financing: bool,
) -> dict:
  """Saves the structured results of a lead qualification call to the CRM.

  Use this after you have gathered all necessary information.

   Args:
       lead_id: The unique ID of the lead.
       is_qualified: True if the lead is qualified for sales follow-up, False otherwise.
       summary: A brief summary of the conversation.
       timeline: The lead's timeline for making a decision (e.g., "Next 3 months").
       needs: A description of the lead's needs.
       has_authority: True if the lead is a decision-maker.
       financing: True if the lead has a confirmed budget.

   Returns:
       A dictionary confirming the status of the operation.
  """
  logging.info("TOOL: Recording qualification data for lead_id: %s", lead_id)
  payload = {
      "is_qualified": is_qualified,
      "summary": summary,
      "timeline": timeline,
      "needs": needs,
      "has_authority": has_authority,
      "financing": financing,
  }
  # In a real app, this would be an async call
  # await crm_service.update_lead_record(...)
  crm_service.update_lead_record(lead_id, "Contacted - Qualified", payload)
  return {"status": "success", "message": "Lead data recorded successfully."}
