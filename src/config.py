"""Settings for the Lead Qualification Voice Agent."""

import pydantic_settings

SettingsConfigDict = pydantic_settings.SettingsConfigDict
BaseSettings = pydantic_settings.BaseSettings


class Settings(BaseSettings):
  """Settings for the Lead Qualification Voice Agent."""

  model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')
  APP_NAME: str = 'Lead Qualification Voice Agent'
  # LLM Provider
  GOOGLE_PROJECT_ID: str
  GOOGLE_LOCATION: str
  GOOGLE_GENAI_USE_VERTEX_AI: str
  GOOGLE_API_KEY: str

  # Telephony Service
  TWILIO_ACCOUNT_SID: str
  TWILIO_AUTH_TOKEN: str
  TWILIO_VIRTUAL_PHONE_NUMBER: str

  BASE_URL: str = 'https://twilio-agent-682040119888.us-central1.run.app'


settings = Settings()
