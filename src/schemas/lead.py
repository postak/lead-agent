"""Pydantic schemas for data validation and serialization."""

import pydantic

Field = pydantic.Field
EmailStr = pydantic.EmailStr
BaseModel = pydantic.BaseModel


class LeadWebhookPayload(BaseModel):
  """Defines the  data structure for a new lead webhook."""

  lead_id: str = Field(
      ..., description="Unique identifier for the lead from the source system."
  )
  first_name: str = Field(
      ..., description="The first name of the potential customer."
  )
  last_name: str = Field(
      ..., description="The last name of the potential customer."
  )
  phone_number: str = Field(
      ..., description="The phone number to call for qualification."
  )
  email: EmailStr = Field(..., description="The lead's email address.")
  product_interest: str | None = Field(
      None, description="The product or service the lead is interested in."
  )
