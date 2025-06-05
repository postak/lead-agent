"""Pydantic schemas for data validation and serialization."""

from pydantic import BaseModel, Field, EmailStr


class LeadWebhookPayload(BaseModel):
  """Defines the  data structure for a new lead webhook."""

  lead_id: str = Field(
      ..., description="Unique identifier for the lead from the source system."
  )
  full_name: str = Field(
      ..., description="The full name of the potential customer."
  )
  phone_number: str = Field(
      ..., description="The phone number to call for qualification."
  )
  email: EmailStr = Field(..., description="The lead's email address.")
  product_interest: str | None = Field(
      None, description="The product or service the lead is interested in."
  )
