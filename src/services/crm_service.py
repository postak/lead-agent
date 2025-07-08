"""Mocked CRM Service.

In a real application, this would use the HubSpot/Salesforce client
to fetch and update contact/lead data.
"""
import asyncio
import logging


class MockCRMService:
  """Mocks interactions with a CRM like HubSpot."""

  async def get_contact_history(self, email: str) -> dict[str, bool | str | None]:
    """Simulates checking if a contact exists and getting their history."""
    logging.info("CRM_SERVICE: Checking history for %s...", email)
    await asyncio.sleep(1)
    if "jane.doe" in email:
      return {
          "contact_exists": True,
          "notes": (
              "Previously downloaded 'GutterGuard Pro' whitepaper on 2025-05-15."
          ),
      }
    return {"contact_exists": False, "notes": None}

  async def update_lead_record(
      self, lead_id: str, status: str, qualification_data: dict[str, str]
  ):
    """Simulates updating the lead record in the CRM."""
    logging.info(
        "CRM_SERVICE: Updating lead %s with status '%s'.", lead_id, status
    )
    logging.info("CRM_SERVICE: Writing data: %s", qualification_data)
    await asyncio.sleep(1)
    logging.info("CRM_SERVICE: Update successful.")
    return {"success": True, "lead_id": lead_id}


# Singleton instance
crm_service = MockCRMService()
